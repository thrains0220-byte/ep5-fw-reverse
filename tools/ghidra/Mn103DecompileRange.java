// Mn103DecompileRange.java — 反编译指定地址范围内的所有函数
// 用法: -postScript Mn103DecompileRange.java <outFile> <loAddr> <hiAddr>
// @category EP5
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.Address;
import java.io.*;
import java.util.*;

public class Mn103DecompileRange extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "decomp_range.txt";
        Address lo = toAddr(Long.decode(args[1]));
        Address hi = toAddr(Long.decode(args[2]));

        DecompInterface di = new DecompInterface();
        di.setOptions(new DecompileOptions());
        di.toggleCCode(true);
        di.setSimplificationStyle("decompile");
        if (!di.openProgram(currentProgram)) {
            println("Mn103DecompileRange: 打开程序失败 " + di.getLastMessage());
            return;
        }
        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        FunctionManager fm = currentProgram.getFunctionManager();
        FunctionIterator fi = fm.getFunctions(lo, true);
        int n = 0;
        while (fi.hasNext()) {
            Function f = fi.next();
            if (f.getEntryPoint().compareTo(hi) > 0) break;
            n++;
            pw.println("==================================================================");
            pw.println("FUNCTION " + f.getName() + "  entry=" + f.getEntryPoint()
                    + "  size=" + f.getBody().getNumAddresses());
            DecompileResults res = di.decompileFunction(f, 90, monitor);
            if (res == null || !res.decompileCompleted() || res.getDecompiledFunction() == null) {
                pw.println("  (反编译失败)");
                continue;
            }
            pw.println(res.getDecompiledFunction().getC());
        }
        pw.flush(); pw.close();
        di.dispose();
        println("Mn103DecompileRange DONE: " + n + " 个函数 -> " + outFile);
    }
}
