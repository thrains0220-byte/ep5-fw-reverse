// Mn103FindArtRefs.java — 在已分析的 E-P5 块 0 中找出所有引用 art_* 字符串区的指令
// 用法: -postScript Mn103FindArtRefs.java <outFile> <loAddr> <hiAddr>
// @category EP5
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.address.Address;
import java.io.*;
import java.util.*;

public class Mn103FindArtRefs extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "artrefs.txt";
        long lo = args.length > 1 ? Long.decode(args[1]) : 0x40714000L;
        long hi = args.length > 2 ? Long.decode(args[2]) : 0x40718000L;

        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        pw.println("# Mn103FindArtRefs  range 0x" + Long.toHexString(lo)
                + "..0x" + Long.toHexString(hi));
        pw.println("# program = " + currentProgram.getName());

        FunctionManager fm = currentProgram.getFunctionManager();
        Listing listing = currentProgram.getListing();
        InstructionIterator it = listing.getInstructions(true);
        int hits = 0, insn = 0;
        Map<String, Integer> byFunc = new TreeMap<>();
        while (it.hasNext()) {
            Instruction i = it.next();
            insn++;
            if ((insn & 0xFFFFF) == 0) {
                if (monitor.isCancelled()) break;
                println("  scanned " + insn);
            }
            long hitVal = -1;
            try {
                int nops = i.getNumOperands();
                for (int r = 0; r < nops && hitVal < 0; r++) {
                    Object[] objs = i.getOpObjects(r);
                    if (objs == null) continue;
                    for (Object o : objs) {
                        if (o instanceof Scalar) {
                            long v = ((Scalar) o).getUnsignedValue();
                            if (v >= lo && v <= hi) { hitVal = v; break; }
                        }
                    }
                }
            } catch (Exception e) {
                // 忽略单条异常
            }
            if (hitVal < 0) continue;
            hits++;
            Function f = fm.getFunctionContaining(i.getAddress());
            String fn = (f != null) ? f.getName() : "<none>";
            byFunc.merge(fn, 1, Integer::sum);
            pw.printf("0x%s  fn=%-22s  %-26s  op=0x%s%n",
                    i.getAddress(), fn, i.toString(), Long.toHexString(hitVal));
        }
        pw.println();
        pw.println("# scanned instructions: " + insn);
        pw.println("# instruction hits: " + hits);
        pw.println("# distinct functions: " + byFunc.size());
        pw.println();
        pw.println("# --- per function counts (top 300) ---");
        byFunc.entrySet().stream()
           .sorted((a, b) -> b.getValue() - a.getValue())
           .limit(300)
           .forEach(e -> pw.println(String.format("%6d  %s", e.getValue(), e.getKey())));
        pw.flush();
        pw.close();
        println("Mn103FindArtRefs DONE: scanned=" + insn + " hits=" + hits
                + " funcs=" + byFunc.size() + " -> " + outFile);
    }
}
