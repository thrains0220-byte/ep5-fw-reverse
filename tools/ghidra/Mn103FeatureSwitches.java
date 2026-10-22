// Mn103FeatureSwitches.java — 枚举块 0 内所有「特性开关」型 RAM 全局
//
// 判定规则：某 RAM 全局若
//   (a) 被 BTST（位测试）读取 —— 用于"某位是否打开"的判定
//   (b) 且被写为常量/掩码 —— 该位由固件写死
// 就是一类「特性开关」。这是"解锁功能"要改的地方。
//
// 用法: -postScript Mn103FeatureSwitches.java <outFile>
// @category EP5
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.Address;
import java.io.*;
import java.util.*;
import java.util.regex.*;

public class Mn103FeatureSwitches extends GhidraScript {

    private static final Pattern IMM = Pattern.compile("0x([0-9a-fA-F]{6,8})");
    private static final Pattern BTST = Pattern.compile("^BTST", Pattern.CASE_INSENSITIVE);

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "feature_switches.txt";
        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        pw.println("# Mn103FeatureSwitches  program=" + currentProgram.getName());

        FunctionManager fm = currentProgram.getFunctionManager();
        Listing listing = currentProgram.getListing();

        // 全局 -> BTST 使用点
        Map<Long, List<String>> tested = new TreeMap<>();
        Map<Long, List<String>> written = new TreeMap<>();
        Map<Long, List<String>> readOther = new TreeMap<>();

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
            String up = s.toUpperCase();
            boolean isBtst = BTST.matcher(up).find();
            boolean isWrite = up.contains("),D0") || up.contains("),D1")
                    || up.contains("),D2") || up.contains("),D3");
            Matcher m = IMM.matcher(s);
            while (m.find()) {
                long v;
                try {
                    v = Long.parseUnsignedLong(m.group(1), 16);
                } catch (Exception e) {
                    continue;
                }
                if (v < 0x60000000L || v >= 0x61000000L) continue;
                String site = "0x" + i.getAddress() + " " + fn + " : " + s;
                if (isBtst) {
                    tested.computeIfAbsent(v, k -> new ArrayList<>()).add(site);
                } else if (isWrite) {
                    written.computeIfAbsent(v, k -> new ArrayList<>()).add(site);
                } else {
                    readOther.computeIfAbsent(v, k -> new ArrayList<>()).add(site);
                }
            }
        }

        pw.println();
        pw.println("================ 被 BTST 位测试的特性开关 RAM 全局 ================");
        pw.println("共 " + tested.size() + " 个");
        for (Map.Entry<Long, List<String>> e : tested.entrySet()) {
            long v = e.getKey();
            List<String> w = written.get(v);
            pw.printf("  0x%08X   BTST %2d 处, 写 %2d 处%n", v, e.getValue().size(),
                    (w == null) ? 0 : w.size());
            int k = 0;
            for (String s : e.getValue()) {
                if (k++ >= 6) { pw.println("        ..."); break; }
                pw.println("        " + s);
            }
            if (w != null) {
                k = 0;
                for (String s : w) {
                    if (k++ >= 4) { pw.println("        写 ..."); break; }
                    pw.println("      W " + s);
                }
            }
        }
        pw.flush();
        pw.close();
        println("Mn103FeatureSwitches DONE: globals=" + tested.size() + " -> " + outFile);
    }
}
