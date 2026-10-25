// SPDX-License-Identifier: GPL-2.0-or-later
/* Headless libretro core benchmark: runs 600-frame stages and prints FPS.
 * Promoted from ignored target/a12-diagnostics/core-benchmark.c, used for the
 * KNULLI FBNeo core-only baseline (knulli-live-reference/fbneo-core-benchmarks.txt).
 * Usage: core-benchmark CORE.so ROM
 */
#include <dlfcn.h>
#include <malloc.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <stdarg.h>
#include "libretro.h"
static struct retro_variable *vars;
/* A12_BENCH_FRAMEHASH=1: print an FNV-1a hash of every frame (visible bytes
 * only) to compare a core's output before and after an optimisation.
 * A12_BENCH_PRESS=N: hold Start and A for 5 of every N frames (past title,
 * precaution and alignment screens). */
static int hash_frames, press_every, frame_no, bytes_pp = 2;
static unsigned long run_no;
static void log_cb(enum retro_log_level l,const char *fmt,...) { (void)l; va_list ap;va_start(ap,fmt);vfprintf(stderr,fmt,ap);va_end(ap); }
static bool env(unsigned cmd,void *data) {
 switch(cmd) {
 case RETRO_ENVIRONMENT_GET_LOG_INTERFACE: ((struct retro_log_callback*)data)->log=log_cb;return true;
 case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
 case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY: *(const char**)data="/tmp/a12-core-benchmark";return true;
 case RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION: *(unsigned*)data=0;return true;
 case RETRO_ENVIRONMENT_SET_VARIABLES: {
  const struct retro_variable *source=data;size_t count=0;
  while(source[count].key)count++;
  vars=calloc(count+1,sizeof(*vars));
  /* A12_BENCH_OPT="key=value;key=value" overrides an option's first value. */
  const char *opts=getenv("A12_BENCH_OPT");
  for(size_t i=0;i<count;i++) {
   vars[i].key=strdup(source[i].key);
   const char *p=strchr(source[i].value,';');if(!p)continue;
   p++;while(*p==' ')p++;
   size_t n=strcspn(p,"|");
   for(const char *o=opts;o&&*o;){
    size_t len=strcspn(o,";");const char *eq=memchr(o,'=',len);
    if(eq&&(size_t)(eq-o)==strlen(source[i].key)&&!strncmp(o,source[i].key,eq-o)){p=eq+1;n=len-(size_t)(eq-o)-1;}
    o+=len;if(*o==';')o++;
   }
   char *value=malloc(n+1);
   memcpy(value,p,n);value[n]=0;vars[i].value=value;
  }
  return true;
 }
 case RETRO_ENVIRONMENT_GET_VARIABLE: {
  struct retro_variable *v=data;v->value=NULL;
  if(vars)for(int i=0;vars[i].key;i++)if(!strcmp(v->key,vars[i].key)){
   v->value=vars[i].value;return v->value!=NULL;
  }
  return false;
 }
 case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE: *(bool*)data=false;return true;
 case RETRO_ENVIRONMENT_GET_CAN_DUPE: *(bool*)data=true;return true;
 case RETRO_ENVIRONMENT_GET_INPUT_BITMASKS: return true;
 case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
  bytes_pp = *(const enum retro_pixel_format*)data == RETRO_PIXEL_FORMAT_XRGB8888 ? 4 : 2; return true;
 case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
 case RETRO_ENVIRONMENT_SET_CONTROLLER_INFO:
 case RETRO_ENVIRONMENT_SET_GEOMETRY:
 case RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO:
 case RETRO_ENVIRONMENT_SET_ROTATION: return true;
 default: return false;
 }
}
static void video(const void*d,unsigned w,unsigned h,size_t pitch){
 frame_no++;
 if(!hash_frames)return;
 if(!d){printf("hash %d dupe\n",frame_no);return;}
 uint32_t x=2166136261u;
 for(unsigned y=0;y<h;y++){const unsigned char*r=(const unsigned char*)d+y*pitch;for(unsigned i=0;i<w*(unsigned)bytes_pp;i++){x^=r[i];x*=16777619u;}}
 printf("hash %d %08x\n",frame_no,x);
}
static void audio(int16_t l,int16_t r){(void)l;(void)r;}
static size_t batch(const int16_t*d,size_t n){(void)d;return n;}
static void poll(void){}
static int16_t input(unsigned p,unsigned d,unsigned i,unsigned id){(void)i;
 if(press_every<=0||p!=0||d!=RETRO_DEVICE_JOYPAD||(run_no%(unsigned long)press_every)>=5)return 0;
 if(id==RETRO_DEVICE_ID_JOYPAD_MASK)return (1<<RETRO_DEVICE_ID_JOYPAD_START)|(1<<RETRO_DEVICE_ID_JOYPAD_A);
 return id==RETRO_DEVICE_ID_JOYPAD_START||id==RETRO_DEVICE_ID_JOYPAD_A;}
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;}
#define FN(name,args) void (*name)args=dlsym(core,#name)
int main(int argc,char**argv) {
 if(argc!=3)return 2;
 void *core=dlopen(argv[1],RTLD_NOW);if(!core){fprintf(stderr,"%s\n",dlerror());return 1;}
 FN(retro_set_environment,(retro_environment_t)); FN(retro_set_video_refresh,(retro_video_refresh_t));
 FN(retro_set_audio_sample,(retro_audio_sample_t)); FN(retro_set_audio_sample_batch,(retro_audio_sample_batch_t));
 FN(retro_set_input_poll,(retro_input_poll_t)); FN(retro_set_input_state,(retro_input_state_t));
 FN(retro_init,(void)); FN(retro_deinit,(void)); FN(retro_run,(void)); FN(retro_unload_game,(void));
 bool(*load)(const struct retro_game_info*)=dlsym(core,"retro_load_game");
 void(*av)(struct retro_system_av_info*)=dlsym(core,"retro_get_system_av_info");
 if(!retro_init||!load||!retro_run||!av)return 1;
 retro_set_environment(env);retro_set_video_refresh(video);retro_set_audio_sample(audio);retro_set_audio_sample_batch(batch);retro_set_input_poll(poll);retro_set_input_state(input);retro_init();
 struct retro_game_info game={.path=argv[2]};
 /* Cores without need_fullpath expect the content in memory, as RetroArch passes it. */
 void(*sysinfo)(struct retro_system_info*)=dlsym(core,"retro_get_system_info");
 struct retro_system_info si={0};if(sysinfo)sysinfo(&si);
 if(!si.need_fullpath) {
  FILE *f=fopen(argv[2],"rb");if(!f){perror(argv[2]);return 1;}
  fseek(f,0,SEEK_END);long size=ftell(f);rewind(f);
  void *data=malloc(size);if(!data||fread(data,1,size,f)!=(size_t)size){fprintf(stderr,"read failed\n");return 1;}
  fclose(f);game.data=data;game.size=size;
 }
 if(!load(&game)){fprintf(stderr,"load failed\n");return 1;}
 struct retro_system_av_info info;av(&info);
 /* Heap after loading: glibc keeps freed chunks (fordblks) dirty in the heap.
  * A12_BENCH_TRIM=1 returns them to the kernel, as malloc_trim(0) would in a frontend. */
 struct mallinfo2 mi=mallinfo2();
 fprintf(stderr,"heap after load: arena %zu KiB, in use %zu KiB, free %zu KiB\n",mi.arena>>10,mi.uordblks>>10,mi.fordblks>>10);
 if(getenv("A12_BENCH_TRIM")) {
  malloc_trim(0);mi=mallinfo2();
  fprintf(stderr,"heap after malloc_trim: arena %zu KiB, in use %zu KiB, free %zu KiB\n",mi.arena>>10,mi.uordblks>>10,mi.fordblks>>10);
 }
 /* KNULLI's archived baseline used A12_BENCH_WARMUP=60 A12_BENCH_STAGES=1. */
 const char *w=getenv("A12_BENCH_WARMUP"),*n=getenv("A12_BENCH_STAGES");
 hash_frames=getenv("A12_BENCH_FRAMEHASH")!=NULL; press_every=getenv("A12_BENCH_PRESS")?atoi(getenv("A12_BENCH_PRESS")):0;
 int warmup=w?atoi(w):1200,stages=n?atoi(n):3;
 for(int i=0;i<warmup;i++){retro_run();run_no++;}
 for(int stage=0;stage<stages;stage++) {
  double start=now();for(int i=0;i<600;i++){retro_run();run_no++;}double elapsed=now()-start;
  printf("frames %d-%d in %.3f s = %.2f FPS; target %.2f FPS\n",warmup+stage*600,warmup+600+stage*600,elapsed,600/elapsed,info.timing.fps);fflush(stdout);
 }
 /* Peak and current memory of the whole run (core, content, this loader). */
 FILE *st=fopen("/proc/self/status","r");char line[128];
 while(st&&fgets(line,sizeof line,st))if(!strncmp(line,"VmHWM:",6)||!strncmp(line,"RssAnon:",8)||!strncmp(line,"VmSwap:",7))fputs(line,stderr);
 if(st)fclose(st);
 retro_unload_game();retro_deinit();dlclose(core);return 0;
}
