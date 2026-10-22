// Mn103FindEffectSwitch.java — 找出对效果 ID 10/20/30/40/50 做多路比较的函数
// 用途: art_chk_effect / art_GetFilterType 之类的分派逻辑必然要比较这些 ID。
// @category EP5
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.scalar.Scalar;
import java.io.*;
import java.util.*;

public class Mn103FindEffectSwitch extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "effectswitch.txt";
        long[] ids = {10L, 20L, 30L, 40L, 50L};

        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        pw.println("# functions comparing against effect IDs 10/20/30/40/50");

        FunctionManager fm = currentProgram.getFunctionManager();
        FunctionIterator fi = fm.getFunctions(true);
        int n = 0;
        while (fi.hasNext()) {
            Function f = fi.next();
            n++;
            if ((n & 0x4000) == 0) {
                if (monitor.isCancelled()) break;
                println("  funcs " + n);
            }
            Set<Long> found = new TreeSet<>();
            List<String> sites = new ArrayList<>();
            InstructionIterator it = currentProgram.getListing().getInstructions(f.getBody(), true);
            while (it.hasNext()) {
                Instruction i = it.next();
                String t = i.toString().toLowerCase();
                if (!t.startsWith("cmp")) continue;
                try {
                    for (int r = 0; r < i.getNumOperands(); r++) {
                        for (Object o : i.getOpObjects(r)) {
                            if (o instanceof Scalar) {
                                long v = ((Scalar) o).getUnsignedValue();
                                for (long id : ids) {
                                    if (v == id) { found.add(id); sites.add(i.getAddress() + " " + i.toString()); }
                                }
                            }
                        }
                    }
                } catch (Exception e) { }
            }
            if (found.size() >= 3) {
                pw.println("FUNC " + f.getEntryPoint() + " " + f.getName()
                        + "  ids=" + found);
                for (String s : sites) pw.println("      " + s);
            }
        }
        pw.flush();
        pw.close();
        println("Mn103FindEffectSwitch DONE, functions scanned=" + n + " -> " + outFile);
    }
}
