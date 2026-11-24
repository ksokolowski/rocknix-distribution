/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Minimal sd-bus declarations for a host syntax check of a12-splash. */
#include <stdint.h>
typedef struct sd_bus sd_bus;
typedef struct sd_bus_message sd_bus_message;
typedef struct sd_bus_error sd_bus_error;
typedef struct sd_bus_slot sd_bus_slot;
typedef int (*sd_bus_message_handler_t)(sd_bus_message *m, void *userdata, sd_bus_error *ret_error);
int sd_bus_new(sd_bus **ret);
int sd_bus_set_address(sd_bus *bus, const char *address);
int sd_bus_start(sd_bus *bus);
sd_bus *sd_bus_unref(sd_bus *bus);
sd_bus *sd_bus_flush_close_unref(sd_bus *bus);
int sd_bus_process(sd_bus *bus, sd_bus_message **r);
int sd_bus_wait(sd_bus *bus, uint64_t timeout_usec);
int sd_bus_match_signal(sd_bus *bus, sd_bus_slot **ret, const char *sender, const char *path, const char *interface, const char *member, sd_bus_message_handler_t callback, void *userdata);
int sd_bus_call_method(sd_bus *bus, const char *destination, const char *path, const char *interface, const char *member, sd_bus_error *ret_error, sd_bus_message **reply, const char *types, ...);
int sd_bus_get_property_trivial(sd_bus *bus, const char *destination, const char *path, const char *interface, const char *member, sd_bus_error *ret_error, char type, void *ret_ptr);
int sd_bus_get_property_string(sd_bus *bus, const char *destination, const char *path, const char *interface, const char *member, sd_bus_error *ret_error, char **ret);
int sd_bus_message_enter_container(sd_bus_message *m, char type, const char *contents);
int sd_bus_message_read(sd_bus_message *m, const char *types, ...);
sd_bus_message *sd_bus_message_unref(sd_bus_message *m);
