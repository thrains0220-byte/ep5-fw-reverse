#ifndef INCLUDED_ESTIMATELOADADDRESS_HXX
#define INCLUDED_ESTIMATELOADADDRESS_HXX

#include <cstdlib>
#include <cstdio>
#include <vector>
#include <map>
#include <set>
#include <string>
#include <stdexcept>

#include "StdInt.hxx"
#include "StringUtils.hxx"
#include "FileUtils.hxx"
#include "ByteUtils.hxx"

struct ByteRange 
{
	uint32_t offset;
	uint32_t len;
};

// In the E-P1 v1.4 firmware it happens to be that most false positive strings are very short strings, maybe 
// with some newlines in between, e.g.
//"9ol\n
//=0>oH\n
//9ol\n
//=0>o\t\n
//9ol\n
//9oI\n
//9o\0"
//
// We can filter out most of these cases by checking not just minimum string length, but minimum line length 
// within a string. Of course this will not filter out ALL false positives, and it will also filter out some 
// valid strings.
// There is also no guarantee that this method of filtering out false positives works with all kinds of 
// firmwares.
inline bool exceedsMinLineLen(const char *str, size_t len, int minLineLen)
{
	int curLineLen = 0;

	for (size_t i = 0; i < len; ++i)
	{
		if (str[i] == 0x0a || str[i] == 0x0d)
			curLineLen = 0;
		else
			++curLineLen;

		if (curLineLen >= minLineLen)
			return true;
	}

	return false;
}

// Find all printable ASCII strings of a certain minimal length in a block of data.
inline std::vector<ByteRange> findAllPrintableAsciiStrings(const byte *data, size_t len, int minLineLen = 6, bool requireNullTermination = true)
{
	std::vector<ByteRange> result;

	uint32_t offset = 0;
	while (offset < len)
	{
		uint32_t b;
		if (isAsciiPrintable(data[offset]))
		{
			b = offset;
			while (1)
			{
				if (offset == len || data[offset] == '\0')
				{
					uint32_t e = offset;
					ByteRange range;
					range.offset = b;
					range.len = e - b;
					if (exceedsMinLineLen((const char *)&data[range.offset], range.len, minLineLen))
					{
						result.push_back(range);
					}

					break;
				}
				else if (!isAsciiPrintable(data[offset]))
				{
					if (!requireNullTermination)
					{
						uint32_t e = offset;
						ByteRange range;
						range.offset = b;
						range.len = e - b;
						if (exceedsMinLineLen((const char *)&data[range.offset], range.len, minLineLen))
						{
							result.push_back(range);
						}
					}

					break;
				}

				++offset;
			}
		}
		else
		{
			++offset;
		}
	}

	return result;
}

// Find all occurrences which may be "mov addr, A0" (hex: FC DC addr), "mov addr, A1" (hex: FC DD) and "mov addr, D0" (hex: FC CC) 
// assuming data is MN103 machine code.
inline std::map<uint32_t, std::vector<uint32_t> > findAllMn103MovA0A1D0(const byte *data, size_t len, uint32_t minAddr = 0x00000000, uint32_t maxAddr = 0xffffffff)
{
	std::map<uint32_t, std::vector<uint32_t> > refMap;
	// This is a map with each "mov rom_addr, register" @ code_addr -> map<rom_addr, vector<code_addr>>
	// A map is used to group all mov-to-register instructions that reference the same source ROM address 
	// as one entry, to speed up computation.

	for (uint32_t codeAddr = 0; codeAddr < len-6; ++codeAddr)
	{
		// byte[0] = opcode byte (0xfc)
		// byte[1] = dst register byte A0, A1, or D0 (A2, A3, D1, D2, D3 also possible, but seems they aren't used much for strings)
		// byte[2,3,4,5] = src address (absolute address in loaded ROM)
		if (data[codeAddr] == 0xfc && (data[codeAddr+1] == 0xdc || data[codeAddr+1] == 0xdd || data[codeAddr+1] == 0xcc))
		{
			// codeAddr is the offset into the machine code (starting at 0x00000000) with a possible mov-to-register instruction
			// romAddr is the referenced address into the loaded ROM data (starting at the load address); at this address in the ROM there could be ASCII string data
			uint32_t romAddr = *(uint32_t *)&data[codeAddr+2];
			if (romAddr >= minAddr && romAddr <= maxAddr) // if the referenced address is outside of some range, discard it to speed up computation
			{
				std::map<uint32_t, std::vector<uint32_t> >::iterator it = refMap.find(romAddr);
				if (it == refMap.end())
				{
					std::vector<uint32_t> tmp;
					tmp.push_back(codeAddr);
					refMap.insert(std::map<uint32_t, std::vector<uint32_t> >::value_type(romAddr, tmp));
				}
				else
				{
					(*it).second.push_back(codeAddr);
				}
			}
		}
	}

	return refMap;
}

inline std::set<size_t> generateRandomIdxSeq(size_t maxIdx, size_t seqLen)
{
	if (maxIdx > RAND_MAX)
		throw std::runtime_error("Index range exceeds random number generator range.");
	if (seqLen > maxIdx)
		throw std::runtime_error("Sequence length exceeds index range.");

	std::set<size_t> result;
	while (result.size() < seqLen)
	{
		size_t r = ((size_t)rand() % maxIdx);
		result.insert(r); // if r already exists in result, nothing is inserted
	}
	return result;
}

inline uint32_t estimateLoadAddress(const byte *data, size_t len, int maxCandidates, std::string fnOutPath, std::string fnOutBase)
{
	printf("Analyzing MN103 machine code...\n");

	// Get all string addresses and all mov operation addresses:
	std::vector<ByteRange> stringOffsets1 = findAllPrintableAsciiStrings(data, len, 6, true); // there will be a small number of false positives, but probably not enough to mess up stastics
	std::map<uint32_t, std::vector<uint32_t> > movOffsets1 = findAllMn103MovA0A1D0(data, len, 0x30000000, 0xa0000000); // there will be false positives

	if (stringOffsets1.size() == 0)
		printf("Warning: No strings found, can't analyze...\n");

	// Write all string addresses to file:
	FILE *fhStrings = fopen(Path::join(fnOutPath, format("%s.addr_strings_all.txt", fnOutBase.c_str())).c_str(), "wt");
	if (!fhStrings)
		throw std::runtime_error("Couldn't open analysis output file for writing.");

	for (int i = 0; i < (int)stringOffsets1.size(); ++i)
	{
		char *tmp = new char[stringOffsets1[i].len+1];
		tmp[stringOffsets1[i].len] = '\0';
		strncpy(tmp, (const char *)&data[stringOffsets1[i].offset], stringOffsets1[i].len);
		fprintf(fhStrings, "0x%08X:%s\n", stringOffsets1[i].offset, tmp);
		delete[] tmp;
	}

	fclose(fhStrings);

	// Write all mov instruction addresses to file:
	FILE *fhMovs = fopen(Path::join(fnOutPath, format("%s.addr_mov_all.txt", fnOutBase.c_str())).c_str(), "wt");
	if (!fhMovs)
		throw std::runtime_error("Couldn't open analysis output file for writing.");

	for (std::map<uint32_t, std::vector<uint32_t> >::const_iterator it = movOffsets1.begin(); it != movOffsets1.end(); ++it)
	{
		uint32_t addr = (*it).first;
		int freq = (int)(*it).second.size();
		fprintf(fhMovs, "0x%08X:%d\n", addr, freq);
	}

	fclose(fhMovs);

	// Reduce lists a little to speed up operation:
	std::vector<ByteRange> stringOffsets;
	std::map<uint32_t, std::vector<uint32_t> > movOffsets;

	if (maxCandidates > 0 && (int)stringOffsets1.size() > maxCandidates)
	{
		std::set<size_t> r1 = generateRandomIdxSeq(stringOffsets1.size(), maxCandidates);
		for (std::set<size_t>::const_iterator it = r1.begin(); it != r1.end(); ++it)
		{
			stringOffsets.push_back(stringOffsets1[(*it)]);
		}
	}
	else
	{
		stringOffsets = stringOffsets1;
	}
	
	if (maxCandidates > 0 && (int)movOffsets1.size() > maxCandidates)
	{
		std::set<size_t> r2 = generateRandomIdxSeq(movOffsets1.size(), maxCandidates);
		for (std::set<size_t>::const_iterator it = r2.begin(); it != r2.end(); ++it)
		{
			std::map<uint32_t, std::vector<uint32_t> >::const_iterator it2 = movOffsets1.begin();
			std::advance(it2, (*it));
			movOffsets.insert((*it2));
		}
	}
	else
	{
		movOffsets = movOffsets1;
	}

	// Do statistical analysis (slow):
	const int totalNumIterations = (int)stringOffsets.size()*(int)movOffsets.size();
	int iterCount = 0;
	std::map<uint32_t, int> histogram;
	for (int i = 0; i < (int)stringOffsets.size(); ++i)
	{
		for (std::map<uint32_t, std::vector<uint32_t> >::const_iterator j = movOffsets.begin(); j != movOffsets.end(); ++j)
		{
			uint32_t movAddr = (*j).first;
			uint32_t strAddr = stringOffsets[i].offset;
			int movFreq = (int)(*j).second.size();
			uint32_t possibleLoadAddress = movAddr - strAddr; // may wrap
			std::map<uint32_t, int>::const_iterator it = histogram.find(possibleLoadAddress);
			if (it == histogram.end())
			{
				histogram.insert(std::map<uint32_t, int>::value_type(possibleLoadAddress, movFreq));
			}
			else
			{
				int occurrence = (*it).second + movFreq;
				histogram.erase(it);
				histogram.insert(std::map<uint32_t, int>::value_type(possibleLoadAddress, occurrence));
			}

			printf("%.3f%%           \r", iterCount/float(totalNumIterations)*100.0f);

			++iterCount;
		}
	}

	// Find maximum of histogram by reversing map ({addr, freq} -> {freq, addr}):
	std::multimap<int, uint32_t> histogramRev;
	for (std::map<uint32_t, int>::const_iterator it = histogram.begin(); it != histogram.end(); ++it)
	{
		histogramRev.insert(std::multimap<int, uint32_t>::value_type((*it).second, (*it).first));
	}

	FILE *fhHistogram = fopen(Path::join(fnOutPath, format("%s.loadaddr_histogram.txt", fnOutBase.c_str())).c_str(), "wt");
	int dumpCount = 0;
	for (std::multimap<int, uint32_t>::const_reverse_iterator it = histogramRev.rbegin(); it != histogramRev.rend(); ++it)
	{
		fprintf(fhHistogram, "0x%08X, %d\n", (*it).second, (*it).first);
		++dumpCount;
		if (dumpCount > 20000) // first 20k entries of histogram is enough for analysis
			break;
	}
	fclose(fhHistogram);

	uint32_t mostProbableLoadAddress;
	if (histogramRev.size() == 0)
	{
		mostProbableLoadAddress = 0xfffffff;
		printf("Most likely loading address could not be compute.\n");
	}
	else
	{
		mostProbableLoadAddress = (*histogramRev.rbegin()).second;
		printf("Most likely loading address: 0x%08X\n", mostProbableLoadAddress);
	}

	return mostProbableLoadAddress;
}

inline void verifyLoadAddress(const byte *data, size_t len, uint32_t loadAddress, std::string fnOutPath, std::string fnOutBase)
{
	printf("Outputting data for manual verification of found load address...\n");

	std::vector<ByteRange> strings = findAllPrintableAsciiStrings(data, len, 3, true); // try to find as many strings as possible (only slight minLineLen filtering to avoid 1-2 byte ascii bytes, which are very common)
	std::map<uint32_t, std::vector<uint32_t> > movOps = findAllMn103MovA0A1D0(data, len, loadAddress, loadAddress + len); // try to find as many mov operations as possible (min/maxAddr filtering, so only for addresses inside ROM)

	FILE *fhUnrefedStrings = fopen(Path::join(fnOutPath, format("%s.unreferenced_strings.txt", fnOutBase.c_str())).c_str(), "wt");
	FILE *fhRefedStrings = fopen(Path::join(fnOutPath, format("%s.referenced_strings.txt", fnOutBase.c_str())).c_str(), "wt");

	if (!fhUnrefedStrings || !fhRefedStrings)
	{
		throw std::runtime_error("Couldn't open analysis output files for writing.");
	}

	for (int i = 0; i < (int)strings.size(); ++i)
	{
		// See if this string's address is referenced by any of the mov operations:
		// It happens often that findAllPrintableAsciiStrings() mis-estimates the starting byte of a string, 
		// e.g. if there happens to be some code byte(s) just before the start of the string that happen to be printable ASCII.
		// For these cases we also try here all alternative string starting points:
		std::vector<uint32_t> refsFound;
		bool refFound = false;
		int stringStartOffset = 0;
		for (stringStartOffset = 0; stringStartOffset < std::min((int)strings[i].len-1, 10); ++stringStartOffset)
		{
			const uint32_t strAddr = strings[i].offset + stringStartOffset + loadAddress;

			for (std::map<uint32_t, std::vector<uint32_t> >::const_iterator j = movOps.begin(); j != movOps.end(); ++j)
			{
				const uint32_t movAddr = (*j).first;
				if (movAddr == strAddr)
				{
					refsFound.insert(refsFound.end(), (*j).second.begin(), (*j).second.end());
					refFound = true;
					// (don't break)
				}
			}

			if (refFound)
				break;
		}

		if (!refFound)
		{
			stringStartOffset = 0; // if not found, write string with no starting offset
			const uint32_t strOff = strings[i].offset + stringStartOffset;
			const uint32_t strLen = strings[i].len - stringStartOffset;
			char *tmp = new char[strLen+1];
			tmp[strLen] = '\0';
			strncpy(tmp, (const char *)&data[strOff], strLen);
			std::string s = tmp;
			delete[] tmp;

			s = lstrip(s); // remove any leading newlines+whitespace, for nicer printing
			s = rstrip(s); // remove any ending newlines, for nicer printing
			// str_addr_rom_swapped is a endian swapped, load address offset version that you can use to search for references in hex editor
			const uint32_t addrRom = strings[i].offset+stringStartOffset+loadAddress;
			fprintf(fhUnrefedStrings, "%04d:\n", i);
			fprintf(fhUnrefedStrings, "str_addr_file=0x%08X+%d\n", strings[i].offset, stringStartOffset);
			fprintf(fhUnrefedStrings, "str_addr_rom=0x%08X (swapped: 0x%08X)\n", addrRom, swapEndian32(addrRom));
			fprintf(fhUnrefedStrings, "%s\n", s.c_str());
			fprintf(fhUnrefedStrings, "%mov_addr=n/a\n");
			fprintf(fhUnrefedStrings, "\n");
		}
		else
		{
			const uint32_t strOff = strings[i].offset + stringStartOffset;
			const uint32_t strLen = strings[i].len - stringStartOffset;
			char *tmp = new char[strLen+1];
			tmp[strLen] = '\0';
			strncpy(tmp, (const char *)&data[strOff], strLen);
			std::string s = tmp;
			delete[] tmp;

			s = lstrip(s); // remove any leading newlines+whitespace, for nicer printing
			s = rstrip(s); // remove any ending newlines+whitespace, for nicer printing
			// str_addr_rom_swapped is a endian swapped, load address offset version that you can use to search for references in hex editor
			const uint32_t addrRom = strings[i].offset+stringStartOffset+loadAddress;
			fprintf(fhRefedStrings, "%04d:\n", i);
			fprintf(fhRefedStrings, "str_addr_file=0x%08X+%d\n", strings[i].offset, stringStartOffset);
			fprintf(fhRefedStrings, "str_addr_rom=0x%08X (swapped: 0x%08X)\n", addrRom, swapEndian32(addrRom));
			fprintf(fhRefedStrings, "%s\n", s.c_str());
			for (int k = 0; k < (int)refsFound.size(); ++k)
			{
				uint32_t refAddr = refsFound[k]+loadAddress;
				fprintf(fhRefedStrings, "mov_addr=0x%08X\n", refAddr);
			}
			fprintf(fhRefedStrings, "\n");
		}

		printf("%.3f%%           \r", i/float(strings.size()-1)*100.0f);
	}

	fclose(fhUnrefedStrings);
	fclose(fhRefedStrings);

	printf("                               \n");

	// Note:
	// Ideally now the strings printed to "unreferenced_strings.txt" should be empty or contain only "junk" strings.
	// In reality it is probably normal that there will be some "good" strings.
	// This will happen whenever the string isn't referenced directly using "mov string_addr, A0/A1/D0". It looks like 
	// sometimes strings are referenced by accessing a table of address, maybe mov'ed into a different register, etc.
}

#endif

