/* SPDX-License-Identifier: GPL-3.0-or-later
 * Execute E-P5 MAIN color fills, still ISP descriptor builder and ART pool wrappers.
 * No camera, hardware registers, real heap, file service, or firmware writes. */
#include "emu.h"
#define BASE 0x7e101020u
#define LEN 15728576u
#define RAM 0x10000000u
#define SP0 (RAM+0xe000)
#define INPUT (RAM+0x1800)
#define SURFACE (RAM+0x3000)
#define REQ (RAM+0x5400)
#define WORK (RAM+0x6000)
#define PACKET (RAM+0x7000)
#define CALLER (RAM+0x100)
#define SOURCE 0x7e55a9c1u
#define TABLE_BYTES (17u*17u*17u*6u)
static uint8_t *img,mem[65536];
static uint32_t end_pc, heap_result, free_expected;
static int nalloc,nfree,stopped;
uint64_t emu_ns;
static const struct {uint32_t pc; uint8_t bytes[3];} hooks[]={
    {0x7e1c8d90,{0xdf,0,4}}, {0x7e3adecd,{0xdf,0xa0,12}},
    {0x7e60d28e,{0xdf,0x80,8}}, {0x7e60d27a,{0xdf,0,4}},
    {0x7e3fd443,{0xdf,0,4}}, {0x7e3fd45c,{0xdf,0x20,8}},
    {0x7e3fd94a,{0xdf,0,0}}, {0x7e3fd922,{0xdf,0x80,4}},
    {0x7e23e0ff,{0xdf,0xf0,0x50}}, {0x7e23e2fd,{0xdf,0xf0,0x2c}}
};
static void ck(int ok,const char *what) {if(!ok){fprintf(stderr,"%08x: %s\n",PC,what);exit(1);}}
static int inside(uint32_t p,uint32_t n,uint32_t b,uint32_t l)
{return p>=b && (uint64_t)p+n<=(uint64_t)b+l;}
uint8_t *mem_host(uint32_t p,uint32_t n){
    /* Decode uses wider instruction fetches; preserve original trailing bytes at hooks. */
    if(inside(p,n,BASE,LEN))return img+(p-BASE);
    if(inside(p,n,RAM,sizeof mem))return mem+(p-RAM);
    return NULL;
}
uint32_t mem_rd(uint32_t p,int n){
    uint8_t *b=mem_host(p,n); uint32_t v=0;
    if(!b){fprintf(stderr,"%08x: unmapped read %08x\n",PC,p);exit(1);}
    for(int i=0;i<n;i++)v|=(uint32_t)b[i]<<(8*i);
    return v;
}
void mem_wr(uint32_t p,uint32_t v,int n){
    if(!inside(p,n,RAM,sizeof mem)){fprintf(stderr,"%08x: unmapped write %08x\n",PC,p);exit(1);}
    for(int i=0;i<n;i++)mem[p-RAM+i]=(uint8_t)(v>>(8*i));
}
void mem_misaligned(uint32_t a,int n,int wr){fprintf(stderr,"%08x: misaligned %08x/%d/%d\n",PC,a,n,wr);exit(1);}
void soc_tick(uint64_t n){emu_ns+=n;}
uint64_t soc_next_event(void){return emu_ns+1;}
int hle_is_hook(uint32_t pc){
    return pc==end_pc || pc==0x7e1c8d90 || pc==0x7e23e0ff || pc==0x7e23e2fd;
}
int hle_check(cpu_t *c){
    uint32_t *r=c->regs, pc=r[REG_PC];
    if(pc==end_pc){stopped=emu_stop=1;return 1;}
    if(pc==0x7e1c8d90)r[REG_A0]=SURFACE;
    if(pc==0x7e23e0ff){
        ck(r[0]==TABLE_BYTES && r[1]==0 && r[REG_A0]==SOURCE && r[REG_A0+1]==0x4e4,
           "unexpected heap allocation arguments");
        nalloc++;r[0]=heap_result;
    }
    if(pc==0x7e23e2fd){
        ck(r[0]==free_expected && r[1]==0,"unexpected heap release arguments");
        nfree++;
    }
    return 0;
}
static uint32_t *start(uint32_t pc,uint32_t end){
    memset(&cpus[0],0,sizeof cpus[0]);
    cpus[0].regs[REG_PC]=pc;cpus[0].regs[REG_SP]=SP0;
    cpus[0].running=1;cpus[0].irq_level=7;end_pc=end;stopped=emu_stop=0;
    return cpus[0].regs;
}
static void run(void){cpu_run(50000,0);ck(stopped && cpus[0].regs[REG_SP]==SP0,"did not reach stop with balanced stack");}
static void color(int play,unsigned r,unsigned g,unsigned b){
    uint32_t *regs=start(play?0x7e60f261:0x7e3baa9e,play?0x7e60f2cb:0x7e3babbb);
    memset(mem+(SURFACE-RAM-4),0xa5,4104);
    if(play){
        mem_wr(SP0+4,INPUT,4);mem_wr(SP0+40,WORK,4);
        mem_wr(INPUT+72,r,2);mem_wr(INPUT+74,g,2);mem_wr(INPUT+76,b,2);
        mem_wr(WORK,SURFACE,4);mem_wr(WORK+4,8,2); /* 8-pixel pitch */
        mem_wr(WORK+8,4,2);mem_wr(WORK+10,2,2);   /* center (4,2) */
        mem_wr(WORK+12,4,2);mem_wr(WORK+14,2,2);  /* x=[2,6), y=[1,3) */
    }else{
        regs[REG_A0]=INPUT;
        mem_wr(INPUT+16,r,1);mem_wr(INPUT+17,g,1);mem_wr(INPUT+18,b,1);
    }
    run();
    if(!play)ck(regs[REG_A0]==SP0+12 && mem_rd(SP0+12,4)==SURFACE &&
                mem_rd(SP0+12+194,1)==21,"MOV ISP source and mode");
    uint32_t word=mem_rd(SURFACE+(play?20:0),4);
    for(int i=-1;i<1025;i++){
        int fill=play?(i==5||i==6||i==9||i==10):(i>=0 && i<1024);
        ck(mem_rd(SURFACE+4*i,4)==(fill?word:0xa5a5a5a5u),"fill/canary mismatch");
    }
    printf("%08x\n",word);
}
static void pinhole(void){
    uint32_t *r=start(0x7e4013b5,0x7e401438);
    /* A2=request, A3=local geometry, D3=packet (not the same as A3). */
    r[REG_A0+2]=REQ;r[REG_A0+3]=SP0+0x18;r[2]=REQ+96;r[3]=PACKET;
    mem_wr(REQ+96,WORK+0x280,4); /* previously initialized request substructure */
    mem_wr(SP0+16,WORK,4);mem_wr(WORK+36,INPUT,4);mem_wr(WORK+32,INPUT+0x200,4);
    mem_wr(PACKET+76,SURFACE,4);mem_wr(PACKET+80,4608,2);mem_wr(PACKET+82,3456,2);
    run();
    ck(mem_rd(REQ+194,1)==21 && mem_rd(REQ+16,4)==SURFACE && mem_rd(REQ,4)==INPUT &&
       mem_rd(REQ+106,2)==4608 && mem_rd(REQ+110,2)==3456 &&
       r[REG_A0]==REQ && r[REG_A0+1]==PACKET && r[0]==0x40000 && r[1]==0x139,
       "pinhole submission fields");
    printf("pinhole 4608 3456 21\n");
}
static uint32_t call(uint32_t fn,int alloc,uint32_t ptr,uint32_t handle){
    uint32_t *r=start(CALLER,CALLER+7);
    mem_wr(CALLER,0xdd,1);mem_wr(CALLER+1,fn-CALLER,4);
    mem_wr(CALLER+5,alloc?0xf0:0xc0,1);mem_wr(CALLER+6,alloc?32:12,1);
    r[0]=alloc?TABLE_BYTES:handle;r[1]=alloc?0:3;
    r[REG_A0]=ptr;r[REG_A0+1]=SOURCE;
    mem_wr(SP0+4,3,4);mem_wr(SP0+8,0x4e4,4);
    heap_result=free_expected=handle;run();return r[0];
}
static void pool(int fail){
    /* Unmapped backend tokens ensure this does not mistake debug/real RAM for a heap. */
    const uint32_t active=0x21000000u, standby=0x21010000u;
    ck(call(0x7e40a3fc,1,WORK,active)==0 && mem_rd(WORK,4)==active,"active alloc");
    mem_wr(WORK+4,0xffffffffu,4);
    ck(call(0x7e40a3fc,1,WORK+4,fail?0:standby)==(fail?65535:0) &&
       mem_rd(WORK+4,4)==(fail?0:standby) && mem_rd(WORK,4)==active,"standby alloc");
    if(!fail)call(0x7e40a4f0,0,0,standby);
    call(0x7e40a4f0,0,0,active);
    ck(nalloc==2 && nfree==(fail?1:2),"backend call counts");
    printf("pool %d %d\n",nalloc,nfree);
}
int main(int argc,char **argv){
    if(argc<3)return 2;
    FILE *f=fopen(argv[1],"rb");img=malloc(LEN);
    if(!f||!img||fread(img,1,LEN,f)!=LEN||fgetc(f)!=EOF)return 2;
    fclose(f);
    for(size_t i=0;i<sizeof hooks/sizeof *hooks;i++)memcpy(img+(hooks[i].pc-BASE),hooks[i].bytes,3);
    if(!strcmp(argv[2],"pinhole"))pinhole();
    else if(!strcmp(argv[2],"pool") && argc==4)pool(atoi(argv[3]));
    else if((!strcmp(argv[2],"play")||!strcmp(argv[2],"mov")) && argc==6)
        color(!strcmp(argv[2],"play"),atoi(argv[3]),atoi(argv[4]),atoi(argv[5]));
    else return 2;
    free(img);return 0;
}
