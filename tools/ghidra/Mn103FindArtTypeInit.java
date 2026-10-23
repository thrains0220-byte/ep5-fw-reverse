// Mn103FindArtTypeInit.java — 找出所有「按类型初始化」调用的调用点与类型实参
//
// 背景（第十四/十九轮）:
//   FUN_40788616(t)  通用按类型初始化:  t == 2 -> 拍照路径, 否则 -> 录像路径
//   FUN_4078866A(t)  star_light 专用按类型初始化（同结构）
//   每个艺术滤镜模块的初始化函数会调用其中之一，
//   **只调 t=2 而不调 t=1 的模块 ⇒ 该滤镜的录像形态未被初始化**（= 被锁）。
//
// 用法: -postScript Mn103FindArtTypeInit.java <outFile> [targetAddrHex ...]
// @category EP5
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.scalar.Scalar;
import java.io.*;
import java.util.*;

public class Mn103FindArtTypeInit extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "arttypeinit.txt";
        long[] targets = {0x40788616L, 0x4078866AL};
        if (args.length > 1) {
            targets = new long[args.length - 1];
            for (int i = 1; i < args.length; i++) targets[i - 1] = Long.decode(args[i]);
        }
        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        FunctionManager fm = currentProgram.getFunctionManager();
        Listing listing = currentProgram.getListing();

        for (long t : targets) {
            String ts = Long.toHexString(t).toUpperCase();
            pw.println("=========== 目标 0x" + ts + " ===========");
            InstructionIterator it = listing.getInstructions(true);
            int n = 0, hits = 0;
            while (it.hasNext()) {
                Instruction i = it.next();
                n++;
                if ((n & 0x20000) == 0 && monitor.isCancelled()) break;
                String s = i.toString().toUpperCase();
                if (!s.startsWith("CALL")) continue;
                if (!s.contains(ts)) continue;
                hits++;
                Function f = fm.getFunctionContaining(i.getAddress());
                // 往前找最近的「立即数装载」作为实参
                String arg = "?";
                Instruction p = i.getPrevious();
                int back = 0;
                while (p != null && back < 6) {
                    String ps = p.toString().toUpperCase();
                    if (ps.contains("MOV 0X")) {
                        int k = ps.indexOf("MOV 0X");
                        String hex = ps.substring(k + 5).trim();
                        int sp = hex.indexOf(' ');
                        if (sp > 0) hex = hex.substring(0, sp);
                        try { arg = String.valueOf(Integer.parseInt(hex, 16)); } catch (Exception e) {}
                        break;
                    }
                    if (ps.contains("MOV ") && (ps.contains(",D0") || ps.contains(",D1") || ps.contains(",D2"))) {
                        int k = ps.indexOf("MOV 0X");
                        if (k < 0) { arg = ps.substring(4).trim(); break; }
                    }
                    p = p.getPrevious();
                    back++;
                }
                pw.println("  0x" + i.getAddress() + "  fn=" +
                    ((f == null) ? "<none>" : f.getName()) + "   arg=" + arg + "   | " + s);
            }
            pw.println("  -> 共 " + hits + " 处\n");
        }
        pw.flush(); pw.close();
        println("Mn103FindArtTypeInit DONE -> " + outFile);
    }
}
