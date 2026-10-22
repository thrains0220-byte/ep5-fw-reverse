// Mn103SeedFunctions.java — 在"前一条指令是返回指令"的位置补建函数
//
// 背景：批量分析只在 CALL 目标处建函数，因此"只被别的函数调用一次"或
//       "仅由返回点进入"的函数会缺失。艺术滤镜分派器所在的区域就是这样。
// 本脚本遍历全部指令，凡是前一条为 RET/RETF/RET imm 的位置，都建一个函数。
//
// 用法: -postScript Mn103SeedFunctions.java <outFile> [loAddr] [hiAddr]
// @category EP5
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.Address;
import java.io.*;
import java.util.*;

public class Mn103SeedFunctions extends GhidraScript {

    private boolean isReturn(Instruction i) {
        String m = i.getMnemonicString().toUpperCase();
        return m.startsWith("RET");
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "seeded.txt";
        Address lo = args.length > 1 ? toAddr(Long.decode(args[1])) : null;
        Address hi = args.length > 2 ? toAddr(Long.decode(args[2])) : null;

        FunctionManager fm = currentProgram.getFunctionManager();
        Listing listing = currentProgram.getListing();

        List<Address> seeds = new ArrayList<>();
        Instruction prev = null;
        InstructionIterator it = listing.getInstructions(true);
        while (it.hasNext()) {
            Instruction i = it.next();
            if (lo != null && i.getAddress().compareTo(lo) < 0) { prev = i; continue; }
            if (hi != null && i.getAddress().compareTo(hi) > 0) break;
            if (prev != null && isReturn(prev)) {
                seeds.add(i.getAddress());
            }
            prev = i;
        }

        int created = 0;
        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        for (Address a : seeds) {
            if (fm.getFunctionAt(a) != null) continue;
            Function f = createFunction(a, null);
            if (f != null) {
                created++;
                pw.println("  created " + f.getName() + " @ " + a
                        + "  body=" + f.getBody());
            }
        }
        pw.flush(); pw.close();
        println("Mn103SeedFunctions DONE: seeds=" + seeds.size() + " created=" + created
                + " total=" + fm.getFunctionCount() + " -> " + outFile);
    }
}
