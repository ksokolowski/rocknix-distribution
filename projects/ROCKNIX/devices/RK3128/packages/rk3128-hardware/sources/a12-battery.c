// SPDX-License-Identifier: GPL-2.0-or-later
/* Monitoring path adapted from Martin Cerveny's wx8_charger.c and KNULLI 5685dd7. */
#include <linux/gpio/consumer.h>
#include <linux/iio/consumer.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/mutex.h>
#include <linux/platform_device.h>
#include <linux/power_supply.h>
#include <linux/workqueue.h>

#define A12_SAMPLES 5

struct a12_battery {
	struct iio_channel *adc;
	struct gpio_desc *dc, *charging;
	struct power_supply *battery, *usb;
	struct delayed_work work;
	struct mutex lock;
	int voltage, capacity, status, online;
	int samples[A12_SAMPLES], count, next, last_dc;
	bool valid;
};

static int a12_capacity(int mv)
{
	/*
	 * 5 % steps from an idle discharge of the owner's cell: the voltage at
	 * which that share of the runtime was left. 0 % keeps about 23 min
	 * before the cell cuts out; 100 % is a full cell just unplugged, 95 %
	 * lies halfway to 90 %.
	 */
	static const int table[] = {3538, 3583, 3630, 3667, 3702, 3731, 3756,
		3775, 3799, 3818, 3831, 3848, 3865, 3884, 3904, 3922, 3940, 3979,
		4069, 4105, 4140};
	int i;

	if (mv <= table[0])
		return 0;
	for (i = 1; i < ARRAY_SIZE(table); i++)
		if (mv < table[i])
			return ((i - 1) * 100 + (mv - table[i - 1]) * 100 /
				(table[i] - table[i - 1])) / (ARRAY_SIZE(table) - 1);
	return 100;
}

/* One ADC sample wobbles by tens of mV: use the median of the last ones. */
static int a12_median(int *s, int n)
{
	int i, j, v;

	for (i = 1; i < n; i++) {
		v = s[i];
		for (j = i; j > 0 && s[j - 1] > v; j--)
			s[j] = s[j - 1];
		s[j] = v;
	}
	return s[n / 2];
}

/* Announce only what userspace sees change; voltage_now alone is polled. */
static int a12_changed(int valid, int status, int capacity, int online,
		       int new_status, int new_capacity, int new_online)
{
	return !valid || status != new_status || capacity != new_capacity ||
	       online != new_online;
}

/* Returns 1 when the reported state changed, 0 when not, or an error. */
static int a12_sample(struct a12_battery *b)
{
	int mv, ret, dc, charging, i, capacity, status, changed, sorted[A12_SAMPLES];

	ret = iio_read_channel_processed(b->adc, &mv);
	if (ret < 0)
		return ret;
	dc = gpiod_get_value_cansleep(b->dc);
	if (dc < 0)
		return dc;
	charging = gpiod_get_value_cansleep(b->charging);
	if (charging < 0)
		return charging;
	/* Plugging in or out moves the voltage at once: start the window again. */
	if (dc != b->last_dc)
		b->count = 0;
	b->last_dc = dc;
	b->samples[b->next] = mv * 2;
	b->next = (b->next + 1) % A12_SAMPLES;
	if (b->count < A12_SAMPLES)
		b->count++;
	for (i = 0; i < b->count; i++)
		sorted[i] = b->samples[(b->next - 1 - i + A12_SAMPLES) % A12_SAMPLES];
	mv = a12_median(sorted, b->count);
	capacity = a12_capacity(mv);
	status = !dc ? POWER_SUPPLY_STATUS_DISCHARGING :
		charging ? POWER_SUPPLY_STATUS_CHARGING :
		capacity > 90 ? POWER_SUPPLY_STATUS_FULL : POWER_SUPPLY_STATUS_NOT_CHARGING;
	mutex_lock(&b->lock);
	changed = a12_changed(b->valid, b->status, b->capacity, b->online,
			      status, capacity, dc);
	b->voltage = mv * 1000;
	b->capacity = capacity;
	b->online = dc;
	b->status = status;
	b->valid = true;
	mutex_unlock(&b->lock);
	return changed;
}

static void a12_battery_work(struct work_struct *work)
{
	struct a12_battery *b = container_of(to_delayed_work(work), struct a12_battery, work);

	if (a12_sample(b) > 0) {
		power_supply_changed(b->battery);
		power_supply_changed(b->usb);
	}
	queue_delayed_work(system_freezable_wq, &b->work, msecs_to_jiffies(5000));
}

static int a12_get_property(struct power_supply *psy, enum power_supply_property prop,
			    union power_supply_propval *val)
{
	struct a12_battery *b = power_supply_get_drvdata(psy);
	int ret = 0;

	mutex_lock(&b->lock);
	if (!b->valid) {
		ret = -ENODATA;
		goto out;
	}
	switch (prop) {
	case POWER_SUPPLY_PROP_STATUS: val->intval = b->status; break;
	case POWER_SUPPLY_PROP_CAPACITY: val->intval = b->capacity; break;
	case POWER_SUPPLY_PROP_VOLTAGE_NOW: val->intval = b->voltage; break;
	case POWER_SUPPLY_PROP_ONLINE: val->intval = b->online; break;
	case POWER_SUPPLY_PROP_PRESENT: val->intval = b->voltage > 0; break;
	case POWER_SUPPLY_PROP_TECHNOLOGY: val->intval = POWER_SUPPLY_TECHNOLOGY_LION; break;
	default: ret = -EINVAL;
	}
out:
	mutex_unlock(&b->lock);
	return ret;
}

static const enum power_supply_property a12_battery_props[] = {
	POWER_SUPPLY_PROP_STATUS, POWER_SUPPLY_PROP_CAPACITY, POWER_SUPPLY_PROP_VOLTAGE_NOW,
	POWER_SUPPLY_PROP_PRESENT, POWER_SUPPLY_PROP_TECHNOLOGY,
};
static const enum power_supply_property a12_usb_props[] = { POWER_SUPPLY_PROP_ONLINE };
static const struct power_supply_desc a12_battery_desc = {
	.name = "battery", .type = POWER_SUPPLY_TYPE_BATTERY,
	.properties = a12_battery_props, .num_properties = ARRAY_SIZE(a12_battery_props),
	.get_property = a12_get_property,
};
static const struct power_supply_desc a12_usb_desc = {
	.name = "usb", .type = POWER_SUPPLY_TYPE_USB,
	.properties = a12_usb_props, .num_properties = ARRAY_SIZE(a12_usb_props),
	.get_property = a12_get_property,
};

static void a12_cancel_work(void *data)
{
	struct a12_battery *b = data;

	cancel_delayed_work_sync(&b->work);
}

static int a12_battery_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct power_supply_config cfg = {};
	struct a12_battery *b;
	int ret;

	b = devm_kzalloc(dev, sizeof(*b), GFP_KERNEL);
	if (!b)
		return -ENOMEM;
	mutex_init(&b->lock);
	b->adc = devm_iio_channel_get(dev, "battery");
	if (IS_ERR(b->adc))
		return dev_err_probe(dev, PTR_ERR(b->adc), "battery ADC\n");
	b->dc = devm_gpiod_get(dev, "dc-detect", GPIOD_IN);
	if (IS_ERR(b->dc))
		return dev_err_probe(dev, PTR_ERR(b->dc), "DC detect GPIO\n");
	b->charging = devm_gpiod_get(dev, "charge-status", GPIOD_IN);
	if (IS_ERR(b->charging))
		return dev_err_probe(dev, PTR_ERR(b->charging), "charge status GPIO\n");
	ret = a12_sample(b);
	if (ret < 0)
		return dev_err_probe(dev, ret, "initial battery sample\n");
	cfg.drv_data = b;
	cfg.fwnode = dev_fwnode(dev);
	b->battery = devm_power_supply_register(dev, &a12_battery_desc, &cfg);
	if (IS_ERR(b->battery))
		return PTR_ERR(b->battery);
	b->usb = devm_power_supply_register(dev, &a12_usb_desc, &cfg);
	if (IS_ERR(b->usb))
		return PTR_ERR(b->usb);
	INIT_DELAYED_WORK(&b->work, a12_battery_work);
	ret = devm_add_action_or_reset(dev, a12_cancel_work, b);
	if (ret)
		return ret;
	platform_set_drvdata(pdev, b);
	queue_delayed_work(system_freezable_wq, &b->work, msecs_to_jiffies(5000));
	return 0;
}

static void a12_battery_shutdown(struct platform_device *pdev)
{
	a12_cancel_work(platform_get_drvdata(pdev));
}

static const struct of_device_id a12_battery_match[] = {
	{ .compatible = "powkiddy,a12-battery" }, { }
};
MODULE_DEVICE_TABLE(of, a12_battery_match);
static struct platform_driver a12_battery_driver = {
	.probe = a12_battery_probe,
	.shutdown = a12_battery_shutdown,
	.driver = { .name = "a12-battery", .of_match_table = a12_battery_match },
};
module_platform_driver(a12_battery_driver);
MODULE_AUTHOR("Martin Cerveny (original WX8 driver)");
MODULE_LICENSE("GPL");
MODULE_IMPORT_NS("IIO_CONSUMER");

MODULE_DESCRIPTION("Powkiddy A12 ADC battery monitor");
