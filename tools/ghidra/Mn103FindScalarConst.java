// Mn103FindScalarConst.java —— 在已分析的 program 里按「标量立即数」和
// 「多分支比较链」两类特征定位函数。
//
// 用途（第二十一轮）:
//   社区补丁落点函数 FUN_40b232ec(out*, step) 的语义是
//       step ∈ {6,3,8,9} -> *out = 0x6cc
//       step == 4        -> *out = 0x1c20
//       否则              -> 错误码 0x39040009 / 返回 0x9d06
//   要在 E-P5 v1.8 上找等价函数, 需要:
//     (1) 引用了 0x6cc / 0x1c20 / 0x9d06 / 0x39040009 的函数;
//     (2) 含 >=3 个「CMP #小立即数 + 条件跳转」比较链的函数。
//
// 用法:
//   -postScript Mn103FindScalarConst.java <outFile> <imm1,imm2,...> [minChain]
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.lang.RegisterValue;
import java.io.*;
import java.util.*;

public class Mn103FindScalarConst extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "find_scalar.txt";
        // Ghidra headless 的位置参数解析不可靠（会截断、会把 key=value 拆开），
        // 因此目标集统一从一个纯文本文件读：
        //   args[0] = 输出文件
        //   args[1] = 目标集文件（每行一个十六进制常量；可选行 "chain N"）
        Set<Long> targets = new LinkedHashSet<>();
        int minChain = 3;
        if (args.length > 1 && args[1].trim().length() > 0) {
            java.io.BufferedReader br = new java.io.BufferedReader(
                    new java.io.FileReader(args[1].trim()));
            String ln;
            while ((ln = br.readLine()) != null) {
                ln = ln.trim();
                if (ln.isEmpty() || ln.startsWith("#")) continue;
                if (ln.toLowerCase().startsWith("chain ")) {
                    minChain = Integer.parseInt(ln.substring(6).trim());
                    continue;
                }
                if (ln.toLowerCase().startsWith("0x")) ln = ln.substring(2);
                targets.add(Long.parseLong(ln, 16));
            }
            br.close();
        }

        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        pw.println("# Mn103FindScalarConst program=" + currentProgram.getName());
        pw.println("# targets=" + targets + "  minChain=" + minChain);

        Listing lst = currentProgram.getListing();
        FunctionManager fm = currentProgram.getFunctionManager();

        // ---- 1) 标量常量命中 ----
        Map<Function, TreeSet<Long>> hits = new TreeMap<>(new Comparator<Function>() {
            public int compare(Function a, Function b) {
                return a.getEntryPoint().compareTo(b.getEntryPoint());
            }
        });
        Map<Function, TreeSet<String>> insns = new TreeMap<>(new Comparator<Function>() {
            public int compare(Function a, Function b) {
                return a.getEntryPoint().compareTo(b.getEntryPoint());
            }
        });

        InstructionIterator it = lst.getInstructions(true);
        int nInsn = 0;
        while (it.hasNext()) {
            Instruction ins = it.next();
            nInsn++;
            for (int i = 0; i < ins.getNumOperands(); i++) {
                for (Object o : ins.getOpObjects(i)) {
                    if (!(o instanceof Scalar)) continue;
                    long v = ((Scalar) o).getUnsignedValue();
                    if (!targets.contains(v)) continue;
                    Function f = fm.getFunctionContaining(ins.getAddress());
                    if (f == null) continue;
                    hits.computeIfAbsent(f, k -> new TreeSet<>()).add(v);
                    insns.computeIfAbsent(f, k -> new TreeSet<>())
                         .add(ins.getAddress() + "  " + ins.toString());
                }
            }
        }
        pw.println("# 指令总数 " + nInsn);
        pw.println();
        pw.println("=== A. 引用目标标量的函数 ===");
        for (Map.Entry<Function, TreeSet<Long>> e : hits.entrySet()) {
            pw.println("FUNCTION " + e.getKey().getName()
                    + "  entry=" + e.getKey().getEntryPoint()
                    + "  body=" + e.getKey().getBody()
                    + "  consts=" + hexset(e.getValue()));
            for (String s : insns.get(e.getKey())) pw.println("    " + s);
        }
        pw.println();

        // ---- 2) 比较链：函数内 CMP #imm8 + 条件跳转 的立即数集合 ----
        pw.println("=== B. 比较链（>= " + minChain + " 个不同的 CMP 立即数）===");
        it = lst.getInstructions(true);
        Map<Function, TreeSet<Long>> chains = new TreeMap<>(new Comparator<Function>() {
            public int compare(Function a, Function b) {
                return a.getEntryPoint().compareTo(b.getEntryPoint());
            }
        });
        Map<Function, StringBuilder> chainTxt = new TreeMap<>(new Comparator<Function>() {
            public int compare(Function a, Function b) {
                return a.getEntryPoint().compareTo(b.getEntryPoint());
            }
        });
        while (it.hasNext()) {
            Instruction ins = it.next();
            if (!ins.getMnemonicString().toUpperCase().startsWith("CMP")) continue;
            Long v = null;
            for (int i = 0; i < ins.getNumOperands(); i++) {
                for (Object o : ins.getOpObjects(i)) {
                    if (o instanceof Scalar) { v = ((Scalar) o).getUnsignedValue(); break; }
                }
                if (v != null) break;
            }
            if (v == null || v > 0xFF) continue;
            Function f = fm.getFunctionContaining(ins.getAddress());
            if (f == null) continue;
            chains.computeIfAbsent(f, k -> new TreeSet<>()).add(v);
            chainTxt.computeIfAbsent(f, k -> new StringBuilder())
                 .append("    ").append(ins.getAddress()).append("  ")
                 .append(ins.toString()).append("\n");
        }
        for (Map.Entry<Function, TreeSet<Long>> e : chains.entrySet()) {
            if (e.getValue().size() < minChain) continue;
            pw.println("FUNCTION " + e.getKey().getName()
                    + "  entry=" + e.getKey().getEntryPoint()
                    + "  cmps=" + hexset(e.getValue()));
            pw.print(chainTxt.get(e.getKey()).toString());
        }

        pw.flush(); pw.close();
        println("Mn103FindScalarConst DONE -> " + outFile);
    }

    private String hexset(Collection<Long> c) {
        StringBuilder sb = new StringBuilder("[");
        boolean f = true;
        for (Long v : c) {
            if (!f) sb.append(", ");
            sb.append(String.format("0x%X", v));
            f = false;
        }
        return sb.append("]").toString();
    }
}
