/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef SPLASH_SD_H
#define SPLASH_SD_H
#include "splash-draw.h"
/* Boot mode loop; seconds_path keeps the previous boot duration for pacing,
 * rewritten at ES start only when record is set. */
/* first_boot: the card is not configured yet; stay until ES and record nothing. */
int splash_sd_run(struct splash_frame *f, const struct splash_layout *l, const char *seconds_path, int record,
		  int first_boot);
/* Shutdown mode: "Stopping <unit>" and a bar running down as stop jobs end,
 * until they are done or systemd's bus goes away. */
int splash_sd_stopping(struct splash_frame *f, const struct splash_layout *l);
#endif
