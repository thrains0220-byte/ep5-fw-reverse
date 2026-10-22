#ifndef INCLUDED_CHECKSUM_HXX
#define INCLUDED_CHECKSUM_HXX

#include <cstddef>
#include <cstdio>
#include <stdexcept>
#include "StdInt.hxx"

// Checksum algorithm:
//	datasum + checksum = 0
//	checksum = -datasum
//	datasum = sum of data interpreted as an array of 32 bit, unsigned integers (so len must be multiple of 4)
//	datasum and checksum are 32 bit, unsigned integers (sums exceeding 32 bit range will wrap)
//
// In Olympus FW the checksum of a block is compute over the block's head, *unscrambled* body and tail 
// (excl. 4 last bytes which is the checksum itself, or with the last 4 bytes set to zero).
inline uint32_t computeChecksum(const byte *data, size_t len)
{
	if ((len % 4) != 0)
		throw std::runtime_error("Data size must be a multiple of 4 to compute checksum.");

	if (data == NULL)
		return 0;

	uint32_t checksum = 0;
	const uint32_t *p = (const uint32_t *)(data);

	for (size_t i = 0; i < len/4; ++i)
	{
		checksum -= p[i];
	}

	return checksum;
}

#endif
