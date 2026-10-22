// Mn103FindOffsetStores.java — 找出所有对某结构体偏移（如 +0x6B）做**写**的指令
// 用途: 定位「谁在设置 UI 类型码」这类字段的写入点 —— 那是解锁补丁的落点。
// 用法: -postScript Mn103FindOffsetStores.java <outFile> <disp1> [disp2 ...]
//   disp 形如 0x6b（十六进制或十进制）
// @category EP5
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.address.Address;
import java.io.*;
import java.util.*;

public class Mn103FindOffsetStores extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "stores.txt";
        PrintWriter pw = new PrintWriter(new FileWriter(outFile));

        Set<Long> want = new HashSet<>();
        for (int a = 1; a < args.length; a++) {
            want.add(Long.decode(args[a]));
        }
        pw.println("# looking for stores to displacements: " + want);

        FunctionManager fm = currentProgram.getFunctionManager();
        Listing listing = currentProgram.getListing();
        InstructionIterator it = listing.getInstructions(true);
        int n = 0, hits = 0;
        while (it.hasNext()) {
            Instruction i = it.next();
            n++;
            if ((n & 0x20000) == 0 && monitor.isCancelled()) break;
            String s = i.toString();
            // 只看写指令：含 "(0x..." 且以 MOV/MOVU/MOVL/MOVH/MOVB 开头且目标含括号
            String up = s.toUpperCase();
            if (!up.startsWith("MOV")) continue;
            int par = up.indexOf('(');
            if (par < 0) continue;
            // 目标部分（逗号之后）含 "(" 表示写内存
            int comma = up.indexOf(',');
            if (comma < 0) continue;
            String dst = up.substring(comma + 1);
            if (!dst.contains("(")) continue;

            // 取出所有标量操作数，找位移
            for (int r = 0; r < i.getNumOperands(); r++) {
                for (Object o : i.getOpObjects(r)) {
                    if (o instanceof Scalar) {
                        long v = ((Scalar) o).getUnsignedValue();
                        if (want.contains(v)) {
                            Function f = fm.getFunctionContaining(i.getAddress());
                            pw.println("  0x" + i.getAddress() + "  fn="
                                    + ((f == null) ? "<none>" : f.getName())
                                    + "   " + s);
                            hits++;
                        }
                    }
                }
            }
        }
        pw.println("# instructions scanned=" + n + "  hits=" + hits);
        pw.flush(); pw.close();
        println("Mn103FindOffsetStores DONE hits=" + hits + " -> " + outFile);
    }
}
