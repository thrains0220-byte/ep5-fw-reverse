// Mn103DumpNormalized2.java — 导出归一化反汇编（v2：精确保留 RAM/ROM 地址）
// 归一化规则：
//   * 分支/调用目标 -> T                （重定位噪声）
//   * 指向**镜像自身**的地址 -> A        （代码/数据重排噪声）
//   * RAM 全局 (0x60xxxxxx) 与 mask ROM (0x7Exxxxxx) **原样保留**
//     —— 这两类地址在两版之间稳定，且能标识功能（AF/镜头相关函数会引用它们）
// 用法: -postScript Mn103DumpNormalized2.java <outFile> <contBaseHex>
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.Address;
import java.io.*;
import java.util.*;

public class Mn103DumpNormalized2 extends GhidraScript {

    private static final Set<String> BRANCH = new HashSet<>(Arrays.asList(
            "BEQ", "BNE", "BGE", "BGT", "BLE", "BLT", "BLO", "BHS", "BRA", "JMP",
            "CALL", "BCALL", "BEQL", "BNEL", "BGEU", "BGTU", "BLEU", "BLTU",
            "BEQA", "BNEA", "CALLS", "CALLF"));

    private long contBase = 0;
    private long imgLen = 0;

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "normalized2.txt";
        if (args.length > 1) {
            contBase = Long.decode(args[1]);
        }
        for (ghidra.program.model.mem.MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            if (b.isInitialized() && b.getSize() > 0x100000) {
                imgLen = b.getSize();
            }
        }
        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        pw.println("# Mn103DumpNormalized2 program=" + currentProgram.getName()
                + " contBase=0x" + Long.toHexString(contBase) + " imgLen=" + imgLen);

        FunctionManager fm = currentProgram.getFunctionManager();
        Listing listing = currentProgram.getListing();
        FunctionIterator fi = fm.getFunctions(true);
        int n = 0;
        while (fi.hasNext()) {
            Function f = fi.next();
            n++;
            if ((n & 0x4000) == 0) {
                if (monitor.isCancelled()) break;
                println("  funcs " + n);
            }
            StringBuilder sb = new StringBuilder();
            InstructionIterator it = listing.getInstructions(f.getBody(), true);
            while (it.hasNext()) {
                sb.append(' ').append(normalize(it.next().toString()));
            }
            pw.println(f.getEntryPoint() + "|" + sb);
        }
        pw.flush();
        pw.close();
        println("Mn103DumpNormalized2 DONE: functions=" + n + " -> " + outFile);
    }

    /** 判断一个 16 进制字面量是否是"镜像内地址"。 */
    private boolean isImageAddr(long v) {
        if (v < 0) return false;
        if (contBase != 0 && v >= contBase && v < contBase + imgLen) return true;
        // 导入基址为 0 时，块内绝对寻址就是小偏移
        if (contBase == 0 && v < imgLen && v >= 0x1000) return true;
        return false;
    }

    private String normalize(String text) {
        String t = text.trim();
        String[] parts = t.split("\\s+");
        String mn = parts[0].toUpperCase();
        StringBuilder sb = new StringBuilder(mn);
        for (int i = 1; i < parts.length; i++) {
            String op = parts[i];
            if (BRANCH.contains(mn)) {
                if (op.startsWith("0x")) op = "T";
            } else if (op.startsWith("0x")) {
                long v;
                try {
                    v = Long.parseLong(op.substring(2), 16);
                } catch (Exception e) {
                    v = -1;
                }
                if (isImageAddr(v)) op = "A";
            }
            sb.append(' ').append(op);
        }
        return sb.toString();
    }
}
