// Mn103Decompile.java — 用 Ghidra 反编译器输出指定函数的伪代码（C 风格）
// 用法: -postScript Mn103Decompile.java <outFile> <addr1> [addr2 ...]
// @category EP5
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.Address;
import java.io.*;
import java.util.*;

public class Mn103Decompile extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "decompile.txt";
        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        pw.println("# Mn103Decompile program=" + currentProgram.getName());

        DecompInterface di = new DecompInterface();
        DecompileOptions opts = new DecompileOptions();
        di.setOptions(opts);
        di.toggleCCode(true);
        di.toggleSyntaxTree(true);
        di.setSimplificationStyle("decompile");
        if (!di.openProgram(currentProgram)) {
            pw.println("# 反编译器打开程序失败: " + di.getLastMessage());
            pw.flush(); pw.close();
            println("Mn103Decompile FAILED to open program: " + di.getLastMessage());
            return;
        }

        FunctionManager fm = currentProgram.getFunctionManager();
        for (int a = 1; a < args.length; a++) {
            Address addr = toAddr(Long.decode(args[a]));
            Function f = fm.getFunctionContaining(addr);
            pw.println("==================================================================");
            if (f == null) {
                pw.println("NO FUNCTION at " + addr);
                continue;
            }
            pw.println("FUNCTION " + f.getName() + "  entry=" + f.getEntryPoint()
                    + "  body=" + f.getBody());
            DecompileResults res = di.decompileFunction(f, 60, monitor);
            if (res == null || !res.decompileCompleted()) {
                pw.println("  (反编译失败: " + (res == null ? "null" : res.getErrorMessage()) + ")");
                continue;
            }
            DecompiledFunction df = res.getDecompiledFunction();
            if (df == null) { pw.println("  (无反编译结果)"); continue; }
            pw.println(df.getC());
        }
        pw.flush();
        pw.close();
        di.dispose();
        println("Mn103Decompile DONE -> " + outFile);
    }
}
