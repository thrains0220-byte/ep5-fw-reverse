// Mn103ArtStringRefs.java — 对给定的 art_* 字符串地址，列出 Ghidra 已知的所有引用
// （包括数据引用），并报告所在内存块与邻近数据。
// 用法: -postScript Mn103ArtStringRefs.java <outFile> <addr1> [addr2 ...]
// @category EP5
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.address.*;
import ghidra.program.model.mem.*;
import java.io.*;
import java.util.*;

public class Mn103ArtStringRefs extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "artstrings.txt";
        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        ReferenceManager rm = currentProgram.getReferenceManager();
        Listing listing = currentProgram.getListing();
        Memory mem = currentProgram.getMemory();

        for (int a = 1; a < args.length; a++) {
            Address ad = toAddr(Long.decode(args[a]));
            pw.println("=== target 0x" + ad.toString());
            MemoryBlock mb = mem.getBlock(ad);
            pw.println("    memory block: " + (mb == null ? "<none>" : mb.getName()
                    + "  " + mb.getStart() + ".." + mb.getEnd()));
            Data d = listing.getDataAt(ad);
            pw.println("    defined data at target: " + (d == null ? "<none>" : d.getDataType().getName()));
            ReferenceIterator rit = rm.getReferencesTo(ad);
            List<Reference> refs = new ArrayList<>();
            while (rit.hasNext()) refs.add(rit.next());
            pw.println("    references TO target: " + refs.size());
            for (Reference r : refs) {
                pw.println("       from 0x" + r.getFromAddress() + "  type=" + r.getReferenceType()
                        + "  space=" + r.getFromAddress().getAddressSpace().getName());
            }
            // 邻近字节
            try {
                byte[] buf = new byte[64];
                Address base = ad.subtract(32);
                mem.getBytes(base, buf);
                StringBuilder sb = new StringBuilder("    bytes[-32..+32]: ");
                for (byte b : buf) sb.append(String.format("%02X ", b));
                pw.println(sb.toString());
            } catch (Exception e) {
                pw.println("    (bytes unavailable: " + e + ")");
            }
            pw.println();
        }
        pw.flush();
        pw.close();
        println("Mn103ArtStringRefs DONE -> " + outFile);
    }
}
