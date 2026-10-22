#ifndef INCLUDED_OLYMPUSFWSCRAMBLE_HXX
#define INCLUDED_OLYMPUSFWSCRAMBLE_HXX

#include <cstddef>
#include <cstdio>
#include <stdexcept>

#include "StdInt.hxx"

// Scramble algorithm:
//	1.	XOR all bytes with 0xFF.
//	2.	Shuffle bytes in blocks of 16 bytes like this:
//		Decoded seq: 0123 4567 89ab cdef
//		Encoded seq: 2031 5746 ba98 ecdf
//
// Descramble algorithm:
//	1.	XOR all bytes with 0xFF.
//	2.	Shuffle bytes in blocks of 16 bytes like this:
//		Encoded seq: 0123 4567 89ab cdef
//		Decoded seq: 1302 6475 ba98 decf
//
// Note:
// Because shuffling works on blocks of 16 bytes, len must be a multiple of 16.
// Changing the order of steps 1 and 2 has no effect as the XOR operation is per-byte.

inline void scrambleData(byte *encr, const byte *decr, size_t len)
{
	if ((len % 16) != 0)
		throw std::runtime_error("Data size must be a multiple of 16 to scramble.");

	if (len > 0 && (encr == NULL || decr == NULL))
		throw std::runtime_error("Can't scramble NULL data.");

	if (encr == decr)
		throw std::runtime_error("Can't scramble in-place.");

	// 1. Shuffle bytes in 16 byte chunks:
	for (size_t i = 0; i < len; i += 16)
	{
		encr[i+0] = decr[i+2];
		encr[i+1] = decr[i+0];
		encr[i+2] = decr[i+3];
		encr[i+3] = decr[i+1];

		encr[i+4] = decr[i+5];
		encr[i+5] = decr[i+7];
		encr[i+6] = decr[i+4];
		encr[i+7] = decr[i+6];

		encr[i+8] = decr[i+11];
		encr[i+9] = decr[i+10];
		encr[i+10] = decr[i+9];
		encr[i+11] = decr[i+8];

		encr[i+12] = decr[i+14];
		encr[i+13] = decr[i+12];
		encr[i+14] = decr[i+13];
		encr[i+15] = decr[i+15];
	}

	// 2. XOR with 0xFF:
	for (size_t i = 0; i < len; ++i)
	{
		encr[i] ^= 0xFF;
	}
}

inline void descrambleData(byte *decr, const byte *encr, size_t len)
{
	if ((len % 16) != 0)
		throw std::runtime_error("Data size must be a multiple of 16 to unscramble.");

	if (len > 0 && (encr == NULL || decr == NULL))
		throw std::runtime_error("Can't unscramble NULL data.");

	if (encr == decr)
		throw std::runtime_error("Can't unscramble in-place.");

	// 1. Shuffle bytes in 16 byte chunks:
	for (size_t i = 0; i < len; i += 16)
	{
		decr[i+0] = encr[i+1];
		decr[i+1] = encr[i+3];
		decr[i+2] = encr[i+0];
		decr[i+3] = encr[i+2];

		decr[i+4] = encr[i+6];
		decr[i+5] = encr[i+4];
		decr[i+6] = encr[i+7];
		decr[i+7] = encr[i+5];

		decr[i+8] = encr[i+11];
		decr[i+9] = encr[i+10];
		decr[i+10] = encr[i+9];
		decr[i+11] = encr[i+8];

		decr[i+12] = encr[i+13];
		decr[i+13] = encr[i+14];
		decr[i+14] = encr[i+12];
		decr[i+15] = encr[i+15];
	}

	// 2. XOR with 0xFF:
	for (size_t i = 0; i < len; ++i)
	{
		decr[i] ^= 0xFF;
	}
}

#endif

