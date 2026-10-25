// SPDX-License-Identifier: GPL-2.0-or-later
// Decode a file's video stream with FFmpeg frame threads, nothing else (no ES).
// Usage: a12-avdecode FILE THREADS [LOOPS]
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
	if (argc < 3) { fprintf(stderr, "usage: %s FILE THREADS [LOOPS]\n", argv[0]); return 2; }
	int loops = argc > 3 ? atoi(argv[3]) : 1;
	long frames = 0;
	for (int l = 0; l < loops; l++) {
		AVFormatContext *fmt = NULL;
		if (avformat_open_input(&fmt, argv[1], NULL, NULL) < 0 || avformat_find_stream_info(fmt, NULL) < 0) return 1;
		int si = av_find_best_stream(fmt, AVMEDIA_TYPE_VIDEO, -1, -1, NULL, 0);
		const AVCodec *codec = avcodec_find_decoder(fmt->streams[si]->codecpar->codec_id);
		AVCodecContext *ctx = avcodec_alloc_context3(codec);
		avcodec_parameters_to_context(ctx, fmt->streams[si]->codecpar);
		ctx->thread_count = atoi(argv[2]);
		ctx->thread_type = FF_THREAD_FRAME;
		if (avcodec_open2(ctx, codec, NULL) < 0) return 1;
		AVPacket *pkt = av_packet_alloc();
		AVFrame *frame = av_frame_alloc();
		while (av_read_frame(fmt, pkt) >= 0) {
			if (pkt->stream_index == si && avcodec_send_packet(ctx, pkt) == 0)
				while (avcodec_receive_frame(ctx, frame) == 0) frames++;
			av_packet_unref(pkt);
		}
		avcodec_send_packet(ctx, NULL);
		while (avcodec_receive_frame(ctx, frame) == 0) frames++;
		av_frame_free(&frame); av_packet_free(&pkt);
		avcodec_free_context(&ctx); avformat_close_input(&fmt);
	}
	printf("decoded %ld frames with %s threads\n", frames, argv[2]);
	return 0;
}
