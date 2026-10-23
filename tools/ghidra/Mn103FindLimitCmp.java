// Mn103FindLimitCmp.java —— 找出所有「拿立即数当上限比较」的点，按函数聚类。
//
// 目的（第二十五轮）：
//     社区解锁补丁的本质 = 把一个「出厂限制常量」改大。
//     已知的例子：AF 驱动步数上限 0x6CC(1740) / 0x1C20(7200)。
//     本脚本把块 0 里所有 CMP #imm, Rn 的位置全部列出（附所属函数），
//     用于系统性地找出「限制型常量」——快门/ISO/连拍/降噪/包围曝光等。
//
// 用法:
//   -postScript Mn103FindLimitCmp.java <outFile> <minImm> <maxImm> [sortMode]
//   sortMode: 0=按函数聚类  1=按立即数排序（降序）
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;
import java.io.*;
import java.util.*;

public class Mn103FindLimitCmp extends GhidraScript {
    static class Row {
        String fn; long entry; long addr; long imm; String txt;
        Row(String fn, long e, long a, long i, String t) {
            this.fn = fn; this.entry = e; this.addr = a; this.imm = i; this.txt = t;
        }
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "limitcmp.txt";
        long minImm = args.length > 1 ? Long.decode(args[1]) : 2;
        long maxImm = args.length > 2 ? Long.decode(args[2]) : 0x1000000L;
        int sortMode = args.length > 3 ? Integer.parseInt(args[3]) : 0;

        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        pw.println("# Mn103FindLimitCmp program=" + currentProgram.getName());
        pw.println("# immediate range " + minImm + ".." + maxImm);

        List<Row> rows = new ArrayList<>();
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext()) {
            Instruction ins = it.next();
            String mn = ins.getMnemonicString().toUpperCase();
            if (!mn.startsWith("CMP")) continue;
            Long imm = null;
            for (int i = 0; i < ins.getNumOperands(); i++) {
                for (Object o : ins.getOpObjects(i)) {
                    if (o instanceof Scalar) {
                        long v = ((Scalar) o).getUnsignedValue();
                        if (v >= minImm && v <= maxImm) { imm = v; break; }
                    }
                }
                if (imm != null) break;
            }
            if (imm == null) continue;
            Function f = getFunctionContaining(ins.getAddress());
            String fn = f == null ? "(nofunc)" : f.getName();
            long entry = f == null ? 0 : f.getEntryPoint().getOffset();
            rows.add(new Row(fn, entry, ins.getAddress().getOffset(), imm, ins.toString()));
        }

        pw.println("# hits = " + rows.size());
        pw.println();

        if (sortMode == 1) {
            rows.sort((a, b) -> Long.compare(b.imm, a.imm));
            for (Row r : rows) {
                pw.println(String.format("imm=0x%-8X (%-10d) fn=%s @0x%08X   %s",
                        r.imm, r.imm, r.fn, r.addr, r.txt));
            }
        } else {
            Map<String, List<Row>> byFn = new TreeMap<>();
            for (Row r : rows) byFn.computeIfAbsent(r.fn, k -> new ArrayList<>()).add(r);
            pw.println("# distinct functions = " + byFn.size());
            pw.println();
            for (Map.Entry<String, List<Row>> e : byFn.entrySet()) {
                List<Row> v = e.getValue();
                Set<Long> imms = new TreeSet<>();
                for (Row r : v) imms.add(r.imm);
                List<Long> immList = new ArrayList<>(imms);
                String immStr = (immList.size() > 12
                        ? immList.subList(0, 12).toString() + ",..."
                        : immList.toString());
                pw.println(String.format("FUNCTION %s  entry=0x%08X  cmps=%d  imms=%s",
                        e.getKey(), v.get(0).entry, v.size(), immStr));
                if (v.size() <= 24) {
                    for (Row r : v) {
                        pw.println(String.format("      0x%08X  imm=0x%-8X (%-8d) %s",
                                r.addr, r.imm, r.imm, r.txt));
                    }
                }
                pw.println();
            }
        }
        pw.flush(); pw.close();
        println("Mn103FindLimitCmp DONE -> " + outFile + "  rows=" + rows.size());
    }
}
