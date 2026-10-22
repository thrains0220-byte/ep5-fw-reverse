// Mn103DumpNormalized.java — 导出每个函数的「归一化反汇编」，用于跨版本语义差分
// 归一化规则：
//   * 分支/调用/跳转的目标地址 -> T      （重定位噪声）
//   * 指向镜像自身的绝对地址立即数 -> A  （代码/数据重排噪声）
//   * 其余助记符与操作数原样保留
// 输出：每行  <funcEntry>|<normalized listing>
// 用法: -postScript Mn103DumpNormalized.java <outFile>
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.Address;
import java.io.*;
import java.util.*;

public class Mn103DumpNormalized extends GhidraScript {

    private static final Set<String> BRANCH = new HashSet<>(Arrays.asList(
            "BEQ", "BNE", "BGE", "BGT", "BLE", "BLT", "BLO", "BHS", "BRA", "JMP",
            "CALL", "BCALL", "BEQL", "BNEL", "BGEU", "BGTU", "BLEU", "BLTU"));

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "normalized.txt";
        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        pw.println("# Mn103DumpNormalized  program=" + currentProgram.getName());

        FunctionManager fm = currentProgram.getFunctionManager();
        Listing listing = currentProgram.getListing();
        Address imgStart = null, imgEnd = null;
        for (ghidra.program.model.mem.MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            if (b.isInitialized() && b.getSize() > 0x100000) {
                imgStart = b.getStart();
                imgEnd = b.getEnd();
            }
        }
        final Address is = imgStart, ie = imgEnd;

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
                Instruction i = it.next();
                sb.append(' ').append(normalize(i.toString(), is, ie));
            }
            pw.println(f.getEntryPoint() + "|" + sb);
        }
        pw.flush();
        pw.close();
        println("Mn103DumpNormalized DONE: functions=" + n + " -> " + outFile);
    }

    private String normalize(String text, Address imgStart, Address imgEnd) {
        String t = text.trim();
        String[] parts = t.split("\\s+");
        String mn = parts[0].toUpperCase();
        StringBuilder sb = new StringBuilder(mn);
        for (int i = 1; i < parts.length; i++) {
            String op = parts[i];
            if (BRANCH.contains(mn)) {
                // 分支助记符后可能带条件码后缀，如 BNE.N
                if (op.startsWith("0x")) {
                    op = "T";
                }
            } else if (op.startsWith("0x") && imgStart != null) {
                long v;
                try {
                    v = Long.parseLong(op.substring(2), 16);
                } catch (Exception e) {
                    v = -1;
                }
                if (v >= 0 && imgStart != null) {
                    Address a = toAddr(v);
                    if (a.getAddressSpace().equals(imgStart.getAddressSpace())
                            && a.compareTo(imgStart) >= 0 && a.compareTo(imgEnd) <= 0) {
                        op = "A";
                    }
                }
            }
            sb.append(' ').append(op);
        }
        return sb.toString();
    }
}
