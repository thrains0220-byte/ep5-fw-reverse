#ifndef INCLUDED_OLYMPUSFWBLOCKHEADTAIL_HXX
#define INCLUDED_OLYMPUSFWBLOCKHEADTAIL_HXX

#include "StdInt.hxx"

// Standard structure for block headers and tails:

#pragma pack(push) // remember struct alignment
#pragma pack(1) // set struct alignment to 1 byte
struct BlockHeadTail
{
	byte typeSig[2];
	byte modelSig[2];
	byte zeroPadding1[4]; // XXX: for lens firmware observed to have values 0, 1, 2
	uint32_t loadingAddress;
	uint32_t len;
	uint16_t version;
	byte zeroPadding2[2];
	uint16_t flags;
	byte zeroPadding3[6];
	uint32_t checksum;
};
#pragma pack(pop) // restore struct alignment

// - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

// Structure for Smmmvvvv.BIN file (from service/repair card 
// firmware update package) block tail:

#pragma pack(push) // remember struct alignment
#pragma pack(1) // set struct alignment to 1 byte
struct BlockTailSFile
{
	byte typeSig[2];
	byte modelSig[2];
	byte zeroPadding1[12]; // XXX: possibly contains 0x0000 flags field
	uint32_t checksum;
	uint32_t loadingAddress;
	byte id[4];
	uint16_t version;
	byte zeroPadding2[2];
};
#pragma pack(pop) // restore struct alignment

#endif