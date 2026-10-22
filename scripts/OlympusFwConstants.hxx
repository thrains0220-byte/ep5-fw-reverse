#ifndef INCLUDED_OLYMPUSFWCONSTANTS_HXX
#define INCLUDED_OLYMPUSFWCONSTANTS_HXX

#include <string>
#include <map>
#include <exception>

#include "tinyxml/tinyxml.h"

#include "StdInt.hxx"
#include "StringUtils.hxx"

// helper, convert byte sequence to Intel byte order integer
inline uint16_t sig2int(byte sig[2])
{
	uint16_t tmp; ((byte *)&tmp)[0] = sig[1]; ((byte *)&tmp)[1] = sig[0];
	return tmp;
}

// NOTE: The values here are sequences of two bytes from left to right, not the bytes 
// interpreted as uint16_t's with Intel byte order.
enum BlockSig
{
	BLK_OE = 0x4F45,
	BLK_OM = 0x4F4D,
	BLK_OA = 0x4F41,
	BLK_OL = 0x4F4C
	// (strobe/flash signature?)
};

inline std::string getBlockDescr(byte blockSig[2])
{
	switch (sig2int(blockSig))
	{
		case BLK_OE:	return "E-system body firmware, main microcontroller";
		case BLK_OM:	return "E-system body firmware, SWD/IS microcontroller"; // ?
		case BLK_OA:	return "E-system additional language firmware";
		case BLK_OL:	return "E-system lens firmware";
		default:		return "Unknown block signature";
	}
}

// - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

//// NOTE: The values here are sequences of two bytes from left to right, not the bytes 
//// interpreted as uint16_t's with Intel byte order.
//enum BodyModelSig
//{
////	MODEL_E1	= ??,		// 2003, listed on firmware update page!!
//	MODEL_E3	= 0x0420,
////	MODEL_E10	= ??,		// 2000, too old? (web says can only be updated by service center, for a fee)
////	MODEL_E20	= ??,		// 2001, too old? (web says can only be updated by service center, for a fee)
//	MODEL_E30	= 0x0600,
////	MODEL_E100RS= ??,		// 2000, too old? (probably can only be updated by service center)
//	MODEL_E300	= 0x0120,
//	MODEL_E330	= 0x0360,
////	MODEL_E400	= ??,		// 2006, not listed on firmware update page
//	MODEL_E410	= 0x0480,
////	MODEL_E420	= ??,		// 2008, listed on firmware update page!!
////	MODEL_E450	= ??,		// 2009, not listed on firmware update page
//	MODEL_E500	= 0x0350,
//	MODEL_E510	= 0x0410,
//	MODEL_E520	= 0x0590,
//	MODEL_E600	= 0x0730,
//	MODEL_E620	= 0x0640,
//	MODEL_EP1	= 0x0680,
//	MODEL_EP2	= 0x0700,
//	MODEL_EPL1	= 0x0740,
//
//	// Stylus/mju, etc.:
//	MODEL_UMINI__STYLUS_V		= 0x0240,
//	MODEL_X500__D590Z__C470Z	= 0x0260,
//	MODEL_U40__UD500			= 0x0280,
//	MODEL_UMINIS__STYLUS_VS		= 0x0310,
//	MODEL_UD80__S800			= 0x0320,
//	MODEL_UD600__S600			= 0x0340,
//	MODEL_U720SW__S720SW		= 0x0370,
//	MODEL_U710_U700__S710_S700	= 0x0390,
//	MODEL_U740_U750__S740_U750	= 0x0430,
//	MODEL_U725SW__S725SW		= 0x0440,
//	MODEL_U770__S770SW			= 0x0450,
//	MODEL_U760__S760			= 0x0460,
//	MODEL_U780__S780			= 0x0470,
//	MODEL_U790SW__S790SW		= 0x0490,
//	MODEL_U795SW__S795SW		= 0x0500,
//	MODEL_U830__S830			= 0x0510,
//	MODEL_U840__S840			= 0x0520,
//	MODEL_U1020__S1020			= 0x0530,
//	MODEL_U1010__S1010			= 0x0540,
//	MODEL_U1030SW__S1030SW		= 0x0550,
//	MODEL_U850SW__S850SW		= 0x0560,
//	MODEL_U1050SW__S1050SW		= 0x0630,
//	MODEL_U6000__S6000			= 0x0650,
//	MODEL_U8000__S8000			= 0x0660,
//	MODEL_U9000__S9000			= 0x0670
//};
//
//enum LensModelSig
//{
//	MODEL_MZD17		= 0x0210,
//	MODEL_MZDE1442	= 0x0110,
//	MODEL_OLEX25	= 0x0800,
//	MODEL_ZD1454II	= 0x3500,
//	MODEL_ZD1454	= 0x0500,
//	MODEL_ZD25		= 0x3300,
//	MODEL_ZD35M		= 0x2000,
//	MODEL_ZD40150	= 0x0101,
//	MODEL_ZDE1260SWD = 0x3100,
//	MODEL_ZDE1442	= 0x2300,
//	MODEL_ZDE18180	= 0x0701,
//	MODEL_ZDE35100	= 0x1700,
//	MODEL_ZDE40150	= 0x2400,
//	MODEL_ZDE50200	= 0x0600,
//	MODEL_ZDE70300	= 0x0801,
//	MODEL_ZDE8F		= 0x0601,
//	MODEL_ZDE90250	= 0x0501,
//	MODEL_ZDE918	= 0x3400,
//	MODEL_ZDEC14	= 0x0400,
//	MODEL_ZDEC20	= 0x1000
//};

inline std::string utf8ToPrintableAsciiReplace(std::string s)
{
	std::string printable = "";
	for (std::string::size_type i = 0; i < s.size(); ++i)
	{
		unsigned char c = s[i];
		if (c >= 32 && c < 127)
			printable += (char)c;
		else
			printable += '?';
	}
	return printable;
}

inline std::map<int, std::string> readModelNameTableFromXml(std::string fn)
{
	std::map<int, std::string> result;

	TiXmlDocument doc(fn.c_str());
	bool docOk = doc.LoadFile();
	if (!docOk)
	{
		throw std::runtime_error("Couldn't open model name table XML file.");
	}

	const TiXmlNode *root = doc.RootElement();
	if (!root)
	{
		throw std::runtime_error("Input XML file is invalid (no root element).");
	}

	const TiXmlElement *mapElem = root->ToElement();
	if (!mapElem || mapElem->ValueStr() != "map")
	{
		throw std::runtime_error("Model name table XML file is invalid (no map element).");
	}

	for (const TiXmlElement *entry = mapElem->FirstChildElement(); entry != NULL; entry = entry->NextSiblingElement())
	{
		if (entry->ValueStr() != "entry")
		{
			printf("Warning: Found unexpected XML element, ignoring.\n");
			continue;
		}

		const TiXmlElement *modelIdElem = entry->FirstChildElement("model_id");
		int modelId = convHexStr2Int(modelIdElem->GetText());

		const TiXmlElement *nameElem = entry->FirstChildElement("name");
		std::string name = utf8ToPrintableAsciiReplace(nameElem->GetText());
		
		result.insert(std::map<int, std::string>::value_type(modelId, name));
	}

	return result;
}

inline std::string getModelDescr(byte blockSig[2], byte modelSig[2], const std::map<int, std::string> &modelNameTableEMA, const std::map<int, std::string> &modelNameTableL)
{
	const int16_t blkSigInt = sig2int(blockSig);
	const int16_t modelId = sig2int(modelSig);

	if (blkSigInt == BLK_OE || blkSigInt == BLK_OM || blkSigInt == BLK_OA)
	{
		std::map<int, std::string>::const_iterator it = modelNameTableEMA.find(modelId);
		if (it == modelNameTableEMA.end())
			return "Unknown body model signature";
		else
			return "Olympus " + (*it).second;
	}
	else if (blkSigInt == BLK_OL)
	{
		std::map<int, std::string>::const_iterator it = modelNameTableL.find(modelId);
		if (it == modelNameTableL.end())
			return "Unknown lens model signature";
		else
			return (*it).second;
	}
	else
	{
		return "Unknown block type/model signature combination";
	}

	//switch (sig2int(blockSig))
	//{
	//	case BLK_OE:
	//	case BLK_OM:
	//	case BLK_OA:
	//		switch (sig2int(modelSig))
	//		{
	//			case MODEL_E3:		return "Olympus E-3";
	//			case MODEL_E30:		return "Olympus E-30";
	//			case MODEL_E300:	return "Olympus E-300";
	//			case MODEL_E330:	return "Olympus E-330";
	//			case MODEL_E410:	return "Olympus E-410";
	//			case MODEL_E500:	return "Olympus E-500";
	//			case MODEL_E510:	return "Olympus E-510";
	//			case MODEL_E520:	return "Olympus E-520";
	//			case MODEL_E600:	return "Olympus E-600";
	//			case MODEL_E620:	return "Olympus E-620";
	//			case MODEL_EP1:		return "Olympus E-P1";
	//			case MODEL_EP2:		return "Olympus E-P2";
	//			case MODEL_EPL1:	return "Olympus E-PL1";

	//			case MODEL_UMINI__STYLUS_V:			return "Olympus u-mini,Stylus V";
	//			case MODEL_X500__D590Z__C470Z:		return "Olympus X500,D590Z,C470Z";
	//			case MODEL_U40__UD500:				return "Olympus u-40,STYLUS,u[mju:]DIGITAL 500";
	//			case MODEL_UMINIS__STYLUS_VS:		return "Olympus u-miniS,StylusVS";
	//			case MODEL_UD80__S800:				return "Olympus uD800 / S800";
	//			case MODEL_UD600__S600:				return "Olympus uD600,S600";
	//			case MODEL_U720SW__S720SW:			return "Olympus u720SW,Stylus720SW";
	//			case MODEL_U710_U700__S710_S700:	return "Olympus u710,Stylus710,u700,Stylus700";
	//			case MODEL_U740_U750__S740_U750:	return "Olympus u[mju:]740/750,STYLUS 740/750";
	//			case MODEL_U725SW__S725SW:			return "Olympus u725SW,Stylus 725SW";
	//			case MODEL_U770__S770SW:			return "Olympus u-770,STYLUS 770SW";
	//			case MODEL_U760__S760:				return "Olympus u760,Stylus 760";
	//			case MODEL_U780__S780:				return "Olympus u780,Stylus 780";
	//			case MODEL_U790SW__S790SW:			return "Olympus u-790SW,STYLUS 790SW";
	//			case MODEL_U795SW__S795SW:			return "Olympus u-795SW,STYLUS 795SW";
	//			case MODEL_U830__S830:				return "Olympus u830,Stylus 830";
	//			case MODEL_U840__S840:				return "Olympus u[mju:]840,Stylus 840";
	//			case MODEL_U1020__S1020:			return "Olympus u[mju:]1020,Stylus 1020";
	//			case MODEL_U1010__S1010:			return "Olympus u[mju:]1010,Stylus 1010";
	//			case MODEL_U1030SW__S1030SW:		return "Olympus u[mju:]1030SW,Stylus 1030SW";
	//			case MODEL_U850SW__S850SW:			return "Olympus u[mju:]850SW,Stylus 850SW";
	//			case MODEL_U1050SW__S1050SW:		return "Olympus u1050SW/Stylus1050sw";
	//			case MODEL_U6000__S6000:			return "Olympus u[mju:] TOUGH-6000/STYLUS TOUGH-6000";
	//			case MODEL_U8000__S8000:			return "Olympus u[mju:] TOUGH-8000/STYLUS TOUGH-8000";
	//			case MODEL_U9000__S9000:			return "Olympus u[mju:]-9000/STYLUS-9000";

	//			default:			return "Unknown body model signature";
	//		}
	//		break;
	//	case BLK_OL:
	//		switch (sig2int(modelSig))
	//		{
	//			case MODEL_MZD17:		return "M.ZUIKO DIGITAL 17mm F2.8";
	//			case MODEL_MZDE1442:	return "M.ZUIKO DIGITAL ED 14-42mm F3.5-5.6";
	//			case MODEL_OLEX25:		return "Extension Tube EX-25";
	//			case MODEL_ZD1454II:	return "ZUIKO DIGITAL 14-54mm F2.8-3.5 II";
	//			case MODEL_ZD1454:		return "ZUIKO DIGITAL 14-54mm F2.8-3.5";
	//			case MODEL_ZD25:		return "ZUIKO DIGITAL 25mm F2.8";
	//			case MODEL_ZD35M:		return "ZUIKO DIGITAL 35mm F3.5 Macro";
	//			case MODEL_ZD40150:		return "ZUIKO DIGITAL 40-150mm F3.5-4.5";
	//			case MODEL_ZDE1260SWD:	return "ZUIKO DIGITAL ED 12-60mm F2.8-4.0 SWD";
	//			case MODEL_ZDE1442:		return "ZUIKO DIGITAL ED 14-42mm F3.5-5.6";
	//			case MODEL_ZDE18180:	return "ZUIKO DIGITAL ED 18-180mm F3.5-6.3";
	//			case MODEL_ZDE35100:	return "ZUIKO DIGITAL ED 35-100mm F2.0";
	//			case MODEL_ZDE40150:	return "ZUIKO DIGITAL ED 40-150mm F4.0-5.6";
	//			case MODEL_ZDE50200:	return "ZUIKO DIGITAL ED 50-200mm F2.8-3.5";
	//			case MODEL_ZDE70300:	return "ZUIKO DIGITAL ED 70-300mm F4.0-5.6";
	//			case MODEL_ZDE8F:		return "ZUIKO DIGITAL ED 8mm F3.5 Fisheye";
	//			case MODEL_ZDE90250:	return "ZUIKO DIGITAL ED 90-250mm F2.8";
	//			case MODEL_ZDE918:		return "ZUIKO DIGITAL ED 9-18mm F4.0-5.6";
	//			case MODEL_ZDEC14:		return "Tele Converter EC-14";
	//			case MODEL_ZDEC20:		return "Tele Converter EC-20";
	//			default:				return "Unknown lens model signature";
	//		}
	//		break;
	//	default:
	//		return "Unknown block type/model signature combination";
	//}
}

// - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

// NOTE: The values here are little endian numbers, not a sequence of two bytes.
enum Flags
{
	FLAGS_CODEU	= 0x0000,	// code block (not scrambled) for SWD/IS microcontroller, used in older firmwares (E-410, E-3, E-520, E-30)
	FLAGS_CODE1	= 0x0100,	// code block, used for main microcontroller code and also for SWD/IS microcontroller in newer firmwares (E-P1, E-P2, E-PL1, some mju cameras with IS)
	FLAGS_LANG	= 0x0101,
	FLAGS_IMGS1	= 0x0102,	// main
	FLAGS_SNDS	= 0x0103,	// used in some mju cameras
	FLAGS_IMGS2 = 0x0104,	// used in some mju cameras for photo text overlays
	FLAGS_CODE2 = 0x0105,	// code block, used in some mju cameras
	FLAGS_0106	= 0x0106	// unknown content; all bytes in range [0x00;0x3F]; used in E-30, E-P1, E-P2, E-PL1
};

inline const char *getFlagsDescr(uint16_t flags)
{
	switch (flags)
	{
		case FLAGS_CODEU:	return "Code (not scrambled)";
		case FLAGS_CODE1:	return "Code (1)";
		case FLAGS_LANG:	return "Multi-language strings and fonts";
		case FLAGS_IMGS1:	return "Images (jpg, ico, bmp) (1)";
		case FLAGS_SNDS:	return "Sounds (wav)";
		case FLAGS_IMGS2:	return "Images (jpg, ico, bmp) (2)";
		case FLAGS_CODE2:	return "Code (2)";
		case FLAGS_0106:	return "Block 0x0106, unknown content"; // still unknown
		default:			return "Unknown block type flags";
	}
}

// - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

inline std::string getBlockTypeFn(byte sig[2], uint16_t flags)
{
	uint16_t tmp; ((byte *)&tmp)[0] = sig[1]; ((byte *)&tmp)[1] = sig[0]; // swap bytes for Intel platforms

	std::string fn;

	if (tmp == BLK_OE)
	{
		fn = "main-";
	}
	else if (tmp == BLK_OM)
	{
		fn = "ibis-";
	}
	else if (tmp == BLK_OA)
	{
		fn = "lang-";
	}
	else if (tmp == BLK_OL)
	{
		fn = "lens-";
	}
	else
	{
		fn = "unkn-";
	}

	switch (flags)
	{
		case FLAGS_CODEU:	fn += "code-uu";	break;
		case FLAGS_CODE1:	fn += "code-01";	break;
		case FLAGS_LANG:	fn += "lang";		break;
		case FLAGS_IMGS1:	fn += "imgs-01";	break;
		case FLAGS_SNDS:	fn += "snds";		break;
		case FLAGS_IMGS2:	fn += "imgs-02";	break;
		case FLAGS_CODE2:	fn += "code-02";	break;
		case FLAGS_0106:	fn += "b106";		break;
		default:			fn += "unkn";		break;
	}

	return fn;
}

#endif