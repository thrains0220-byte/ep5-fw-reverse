#include "lut_wheel.h"

static unsigned magnitude(int x) { return (unsigned)(x < 0 ? -x : x); }

int ep5_wheel_valid(const struct ep5_wheel_values *v)
{
    if (!v)
        return 0;
    for (unsigned axis = 0; axis < 3; ++axis)
        for (unsigned i = 0; i < EP5_WHEEL_SECTORS; ++i)
            if (magnitude(v->axis[axis][i]) > (axis == EP5_WHEEL_SAT ? 5u : 15u))
                return 0;
    return 1;
}

int ep5_wheel_same_look(const struct ep5_wheel_edit *a, const struct ep5_wheel_edit *b)
{
    return a && b && a->number && a->number <= 16 && a->picture_mode && a->variant &&
        a->number == b->number && a->picture_mode == b->picture_mode &&
        a->variant == b->variant && a->look_crc == b->look_crc;
}

void ep5_wheel_copy(struct ep5_wheel_edit *out, const struct ep5_wheel_edit *edit)
{
    out->number = edit->number;
    out->picture_mode = edit->picture_mode;
    out->variant = edit->variant;
    out->look_crc = edit->look_crc;
    for (unsigned a = 0; a < 3; ++a)
        for (unsigned i = 0; i < EP5_WHEEL_SECTORS; ++i)
            out->values.axis[a][i] = edit->values.axis[a][i];
}
/* EP5W (v1), little endian, CRC-32/ISO-HDLC over bytes 0..51. */
static uint32_t crc32(const uint8_t *p, unsigned n)
{
    uint32_t crc = UINT32_MAX;
    while (n--) {
        crc ^= *p++;
        for (unsigned i = 0; i < 8; ++i)
            crc = (crc >> 1) ^ ((crc & 1u) ? UINT32_C(0xedb88320) : 0);
    }
    return ~crc;
}
static void put32(uint8_t *p, uint32_t v)
{
    for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(v >> (8*i));
}
static uint32_t get32(const uint8_t *p)
{
    return p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
}
int ep5_wheel_encode(const struct ep5_wheel_edit *edit, uint8_t *p, size_t size)
{
    if (!p || size != EP5_WHEEL_FILE_BYTES || !ep5_wheel_same_look(edit,edit) ||
        !ep5_wheel_valid(&edit->values))
        return 0;
    p[0]='E'; p[1]='P'; p[2]='5'; p[3]='W'; p[4]=1; p[5]=12;
    p[6]=(uint8_t)edit->picture_mode; p[7]=(uint8_t)(edit->picture_mode>>8);
    p[8]=edit->variant; p[9]=(uint8_t)edit->number; p[10]=0; p[11]=0;
    put32(p+12,edit->look_crc);
    for (unsigned a = 0; a < 3; ++a)
        for (unsigned i = 0; i < 12; ++i)
            p[16 + 12*a+i] = (uint8_t)edit->values.axis[a][i];
    put32(p+52, crc32(p,52));
    return 1;
}
int ep5_wheel_decode(const uint8_t *p, size_t size, struct ep5_wheel_edit *out)
{
    if (!out || !p || size != EP5_WHEEL_FILE_BYTES || p[0]!='E' || p[1]!='P' ||
        p[2]!='5' || p[3]!='W' || p[4]!=1 || p[5]!=12 || p[10] || p[11] ||
        get32(p+52)!=crc32(p,52))
        return 0;
    struct ep5_wheel_edit edit;
    edit.picture_mode = (uint16_t)(p[6] | p[7]<<8);
    edit.variant = p[8];
    edit.number = p[9];
    edit.look_crc = get32(p+12);
    for (unsigned a = 0; a < 3; ++a) {
        for (unsigned i = 0; i < 12; ++i) {
            int raw = p[16+12*a+i];
            edit.values.axis[a][i] = (int8_t)(raw >= 128 ? raw-256 : raw);
        }
    }
    if (!ep5_wheel_same_look(&edit,&edit) || !ep5_wheel_valid(&edit.values))
        return 0;
    ep5_wheel_copy(out,&edit);
    return 1;
}

/* Q12 degrees and Q14 trigonometric ratios. No floating-point or libm calls. */
enum { DEGREE = 4096 };
static const int centres[] = {699446, 614638, 529830, 445023, 211555, 86860, 1436726, 1309514, 1182303, 1065569, 948835, 824140};
static const uint16_t positive[] = {225,225,225,240,224,199,232,232,281,374,243,399};
static const uint16_t negative[] = {360,360,370,462,312,240,234,234,370,240,240,240};
static const uint16_t light_steps[] = {0,25,50,100,150,200,250,300,350,400,500,600,700,800,900,1000};
static const uint16_t sine[] = {
    0,286,572,857,1143,1428,1713,1997,2280,2563,2845,3126,3406,3686,3964,4240,
    4516,4790,5063,5334,5604,5872,6138,6402,6664,6924,7182,7438,7692,7943,8192,
    8438,8682,8923,9162,9397,9630,9860,10087,10311,10531,10749,10963,11174,11381,
    11585,11786,11982,12176,12365,12551,12733,12911,13085,13255,13421,13583,13741,
    13894,14044,14189,14330,14466,14598,14726,14849,14968,15082,15191,15296,15396,
    15491,15582,15668,15749,15826,15897,15964,16026,16083,16135,16182,16225,16262,
    16294,16322,16344,16362,16374,16382,16384
};
static const int atan_ratio[] = {
    0,3667,7331,10993,14649,18297,21937,25567,29184,32787,36375,39946,
    43498,47030,50541,54029,57492,60931,64343,67727,71082,74408,77703,80966,
    84198,87396,90560,93691,96786,99846,102870,105859,108810,111726,114604,117445,
    120249,123016,125746,128439,131094,133712,136294,138839,141347,143819,146255,148655,
    151019,153348,155643,157903,160128,162320,164479,166605,168698,170758,172787,174785,
    176752,178689,180595,182472,184320
};

static int sin_q14(int angle)
{
    angle %= 360*DEGREE;
    if (angle < 0) angle += 360*DEGREE;
    int sign = angle >= 180*DEGREE ? -1 : 1;
    angle %= 180*DEGREE;
    if (angle > 90*DEGREE) angle = 180*DEGREE-angle;
    unsigned i = (unsigned)angle / DEGREE;
    int value = sine[i];
    if (i < 90) value += ((sine[i+1]-value)*(angle%DEGREE)+DEGREE/2)/DEGREE;
    return sign*value;
}

static int angle_q12(int x, int y)
{
    unsigned ax = magnitude(x), ay = magnitude(y);
    unsigned hi = ax > ay ? ax : ay, lo = ax > ay ? ay : ax;
    if (!hi) return 0;
    unsigned ratio = lo * 64, i = ratio / hi;
    int angle = atan_ratio[i];
    if (i < 64) angle += (int)((atan_ratio[i+1] - atan_ratio[i]) * (ratio%hi) / hi);
    if (ay > ax) angle = 90*DEGREE-angle;
    if (x < 0) angle = 180*DEGREE-angle;
    return y < 0 ? 360*DEGREE-angle : angle;
}
static unsigned root(unsigned n)
{
    unsigned result = 0;
    for (unsigned bit = 1u<<30; bit; bit >>= 2) {
        if (n >= result+bit) {
            n -= result+bit;
            result = (result>>1)+bit;
        } else result >>= 1;
    }
    return result;
}
static int rounded(int64_t numerator, int denominator)
{
    return (int)((numerator + (numerator >= 0 ? denominator/2 : -denominator/2))/denominator);
}
static uint16_t clip(int v)
{
    return (uint16_t)(v < 0 ? 0 : v > 65535 ? 65535 : v);
}

static void adjust(const struct ep5_wheel_values *v, uint16_t rgb[3])
{
    int r=rgb[0], g=rgb[1], b=rgb[2];
    int cb = rounded(-11058LL*r-21710LL*g+32768LL*b,65536);
    int cr = rounded(32768LL*r-27439LL*g-5329LL*b,65536);
    if (!cb && !cr) return;
    int angle = angle_q12(cb,cr), total=0, sum_h=0, sum_s=0, sum_l=0;
    for (unsigned i = 0; i < EP5_WHEEL_SECTORS; ++i) {
        unsigned distance = magnitude(angle-centres[i]);
        if (distance > 180*DEGREE) distance = 360*DEGREE-distance;
        if (distance >= 30*DEGREE) continue;
        int w = sin_q14(90*DEGREE - (int)distance*3);
        int saturation = v->axis[EP5_WHEEL_SAT][i], light=v->axis[EP5_WHEEL_LIGHT][i];
        total += w;
        sum_h += w * v->axis[EP5_WHEEL_HUE][i];
        sum_s += w * saturation * (saturation < 0 ? negative[i] : positive[i]);
        sum_l += w * (light < 0 ? -1 : 1) * light_steps[magnitude(light)];
    }
    if (!total || (!sum_h && !sum_s && !sum_l)) return;
    int shift = rounded((int64_t)sum_h * (DEGREE*11/2), total); /* 5.5 degrees per step */
    int sat_q14 = 16384 + rounded((int64_t)sum_s * 3 * 16384, total*10000);
    int cosval = sin_q14(90*DEGREE+shift), sinval = sin_q14(shift);
    int cb_diff = rounded(((int64_t)cb*cosval-(int64_t)cr*sinval)*sat_q14, 16384*16384)-cb;
    int cr_diff = rounded(((int64_t)cb*sinval+(int64_t)cr*cosval)*sat_q14, 16384*16384)-cr;
    int dy = 0;
    if (sum_l) {
        unsigned chroma = root((unsigned)((int64_t)cb*cb+(int64_t)cr*cr));
        int fade = chroma >= 16384 ? 65535 : (int)(4*chroma);
        dy = rounded((int64_t)sum_l*fade, total*4096);
    }
    rgb[0] = clip(r + dy + rounded(91881LL*cr_diff,65536));
    rgb[1] = clip(g + dy + rounded(-22553LL*cb_diff-46802LL*cr_diff,65536));
    rgb[2] = clip(b + dy + rounded(116130LL*cb_diff,65536));
}

int ep5_wheel_bake(const struct ep5_wheel_values *v, const uint16_t *base, size_t base_words,
                   uint16_t *dest, size_t dest_words, unsigned first, unsigned count)
{
    if (!ep5_wheel_valid(v) || !dest || dest_words < EP5_LUT_VALUES ||
        (base ? base_words < EP5_LUT_VALUES : base_words != 0) ||
        first > EP5_WHEEL_NODES || count > EP5_WHEEL_NODES-first)
        return 0;
    uintptr_t a=(uintptr_t)base, b=(uintptr_t)dest;
    if (base && a!=b && (a>b ? a-b : b-a) < EP5_LUT_VALUES*sizeof *base)
        return 0;
    int changed = 0;
    for (unsigned axis = 0; axis < 3; ++axis)
        for (unsigned sector = 0; sector < EP5_WHEEL_SECTORS; ++sector)
            if (v->axis[axis][sector])
                changed = 1;
    if (!changed && base == dest)
        return 1;
    for (unsigned i = first; i < first+count; ++i) {
        uint16_t rgb[3];
        unsigned coordinate = i;
        for (unsigned c=0; c<3; ++c) {
            rgb[c] = base ? base[3*i+c] : (uint16_t)(((coordinate%17u)*65535u+8)/16);
            coordinate /= 17;
        }
        if (changed)
            adjust(v,rgb);
        for (unsigned c=0; c<3; ++c) dest[3*i+c]=rgb[c];
    }
    return 1;
}
