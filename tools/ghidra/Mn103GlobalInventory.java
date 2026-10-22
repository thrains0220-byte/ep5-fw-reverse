// Mn103GlobalInventory.java — 块 0 全局接口清单
// 输出三类索引，作为"完全破解"的基础地图：
//   1. RAM 全局 (0x60xxxxxx)：被引用的地址 + 引用次数 + 引用它的函数
//   2. mask ROM 地址 (0x7Exxxxxx)：按 64KB 页聚类 + 计数（未被引用的页 = 未启用资源）
//   3. 每个 RAM 全局被哪些函数写/读（写=设置开关，读=使用）
// 用法: -postScript Mn103GlobalInventory.java <outFile>
// @category EP5
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.symbol.Reference;
import java.io.*;
import java.util.*;
import java.util.regex.*;

public class Mn103GlobalInventory extends GhidraScript {

    private static final Pattern IMM = Pattern.compile("0x([0-9a-fA-F]{6,8})");

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "global_inventory.txt";
        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        pw.println("# Mn103GlobalInventory  program=" + currentProgram.getName());

        FunctionManager fm = currentProgram.getFunctionManager();
        Listing listing = currentProgram.getListing();

        // global -> (readCount, writeCount, set of function names)
        Map<Long, int[]> cnt = new TreeMap<>();
        Map<Long, Set<String>> users = new HashMap<>();
        Map<Long, Set<String>> writers = new HashMap<>();
        Map<Long, Integer> romPage = new TreeMap<>();
        Map<Long, Set<String>> romUsers = new HashMap<>();
        Map<String, Integer> romPageCount = new TreeMap<>();

        InstructionIterator it = listing.getInstructions(true);
        int n = 0;
        while (it.hasNext()) {
            Instruction i = it.next();
            n++;
            if ((n & 0xFFFFF) == 0) {
                if (monitor.isCancelled()) break;
                println("  scanned " + n);
            }
            Function f = fm.getFunctionContaining(i.getAddress());
            String fn = (f == null) ? "<none>" : f.getName();
            String s = i.toString();
            Matcher m = IMM.matcher(s);
            while (m.find()) {
                long v;
                try {
                    v = Long.parseUnsignedLong(m.group(1), 16);
                } catch (Exception e) {
                    continue;
                }
                if (v >= 0x60000000L && v < 0x61000000L) {
                    int[] c = cnt.computeIfAbsent(v, k -> new int[2]);
                    c[0]++;
                    users.computeIfAbsent(v, k -> new TreeSet<>()).add(fn);
                    boolean isWrite = s.toUpperCase().contains("),D0")
                            || s.toUpperCase().contains("),D1")
                            || s.toUpperCase().contains("),D2")
                            || s.toUpperCase().contains("),D3");
                    if (isWrite) {
                        c[1]++;
                        writers.computeIfAbsent(v, k -> new TreeSet<>()).add(fn);
                    }
                } else if (v >= 0x7E000000L && v < 0x80000000L) {
                    long page = v & 0xFFFF0000L;
                    romPage.merge(page, 1, Integer::sum);
                    romUsers.computeIfAbsent(v, k -> new TreeSet<>()).add(fn);
                }
            }
        }

        pw.println();
        pw.println("================ RAM 全局 (0x60xxxxxx) ================");
        pw.println("共 " + cnt.size() + " 个被引用的 RAM 全局");
        for (Map.Entry<Long, int[]> e : cnt.entrySet()) {
            long v = e.getKey();
            int[] c = e.getValue();
            pw.printf("  0x%08X  引用 %3d  写 %3d   被 %d 个函数使用%n",
                    v, c[0], c[1], users.get(v).size());
            if (c[1] > 0) {
                pw.println("        写者: " + join(writers.get(v)));
            }
            if (c[0] <= 4) {
                pw.println("        使用: " + join(users.get(v)));
            }
        }

        pw.println();
        pw.println("================ mask ROM 引用 (0x7Exxxxxx) ================");
        Map<Long, Set<Long>> byPage = new TreeMap<>();
        for (Long v : romUsers.keySet()) {
            byPage.computeIfAbsent(v & 0xFFFF0000L, k -> new TreeSet<>()).add(v);
        }
        pw.println("共 " + byPage.size() + " 个 64KB 页被引用");
        for (Map.Entry<Long, Set<Long>> e : byPage.entrySet()) {
            pw.printf("  页 0x%08X  地址 %4d 个%n", e.getKey(), e.getValue().size());
        }
        pw.println();
        pw.println("---- 每个被引用的 ROM 地址（地址 -> 引用它的函数）----");
        for (Map.Entry<Long, Set<String>> e : romUsers.entrySet()) {
            pw.printf("  0x%08X  %s%n", e.getKey(), join(e.getValue()));
        }
        pw.flush();
        pw.close();
        println("Mn103GlobalInventory DONE: instructions=" + n + " ramGlobals=" + cnt.size()
                + " romPages=" + byPage.size() + " -> " + outFile);
    }

    private String join(Set<String> s) {
        if (s == null) return "";
        StringBuilder sb = new StringBuilder();
        int n = 0;
        for (String x : s) {
            if (n++ >= 8) { sb.append(" ..."); break; }
            if (sb.length() > 0) sb.append(", ");
            sb.append(x);
        }
        return sb.toString();
    }
}
