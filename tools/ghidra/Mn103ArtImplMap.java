// Mn103ArtImplMap.java — 列出所有引用 art 名字带的代码位置及其所属函数
// 用途：art_<effect>_passN / _in / _out 等字符串是**实现函数的调试标签**，
//       引用它们的位置就落在对应实现函数里。
// 用法: -postScript Mn103ArtImplMap.java <outFile> <nameLoAddr> <nameHiAddr>
// @category EP5
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;
import java.io.*;
import java.util.*;
import java.util.regex.*;

public class Mn103ArtImplMap extends GhidraScript {

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "artimpl.txt";
        long lo = Long.decode(args[1]);
        long hi = Long.decode(args[2]);

        FunctionManager fm = currentProgram.getFunctionManager();
        Listing listing = currentProgram.getListing();
        PrintWriter pw = new PrintWriter(new FileWriter(outFile));

        // 名字带内的所有字符串（起始地址 -> 文本）
        Map<Long, String> names = new TreeMap<>();
        Memory mem = currentProgram.getMemory();
        for (long a = lo; a < hi; a += 1) {
            Address ad = toAddr(a);
            if (!mem.contains(ad)) continue;
            StringBuilder sb = new StringBuilder();
            Address p = ad;
            for (int k = 0; k < 48; k++) {
                if (!mem.contains(p)) break;
                int b = mem.getByte(p) & 0xFF;
                if (b == 0) break;
                if (b < 0x20 || b > 0x7E) { sb.setLength(0); break; }
                sb.append((char) b);
                p = p.add(1);
            }
            if (sb.length() >= 8) names.put(a, sb.toString());
        }
        pw.println("# art 名字带 0x" + Long.toHexString(lo) + "..0x" + Long.toHexString(hi)
                + "  可用字符串 " + names.size() + " 条\n");

        // 扫描全部指令，找引用这些地址的
        Pattern IMM = Pattern.compile("0x([0-9a-fA-F]{6,8})");
        Map<String, TreeSet<String>> byEffect = new TreeMap<>();
        Map<String, TreeSet<String>> byFunc = new TreeMap<>();

        InstructionIterator it = listing.getInstructions(true);
        int n = 0;
        while (it.hasNext()) {
            Instruction i = it.next();
            n++;
            if ((n & 0xFFFFF) == 0) {
                if (monitor.isCancelled()) break;
                println("  scanned " + n);
            }
            Matcher m = IMM.matcher(i.toString());
            while (m.find()) {
                long v;
                try {
                    v = Long.parseUnsignedLong(m.group(1), 16);
                } catch (Exception e) {
                    continue;
                }
                String s = names.get(v);
                if (s == null) continue;
                if (!s.startsWith("art_")) continue;
                Function f = fm.getFunctionContaining(i.getAddress());
                String fn = (f == null) ? ("<no-fn@" + i.getAddress()) : f.getName();
                byEffect.computeIfAbsent(s, k -> new TreeSet<>()).add(fn + " @0x" + i.getAddress());
                byFunc.computeIfAbsent(fn, k -> new TreeSet<>()).add(s);
            }
        }

        pw.println("================ 按 art 名字分组 ================");
        for (Map.Entry<String, TreeSet<String>> e : byEffect.entrySet()) {
            pw.println(e.getKey() + "   -> " + e.getValue());
        }
        pw.println();
        pw.println("================ 涉及 art 名字的函数 ================");
        for (Map.Entry<String, TreeSet<String>> e : byFunc.entrySet()) {
            pw.println(e.getKey() + "  (" + e.getValue().size() + " 个 art 名)");
            for (String s : e.getValue()) pw.println("      " + s);
        }
        pw.flush(); pw.close();
        println("Mn103ArtImplMap DONE: names=" + names.size() + " effects=" + byEffect.size()
                + " funcs=" + byFunc.size() + " -> " + outFile);
    }
}
