//Dump MN103 disassembly + function inventory for the Olympus E-P5 firmware.
//
//Usage (analyzeHeadless):
//   -postScript Mn103Dump.java [outDir]
//
//Environment variables honoured by the harness:
//   MN103_RANGE_START / MN103_RANGE_END   (default 0x403B7965 / 0x403B7A30)
//   MN103_FUNC_LO   / MN103_FUNC_HI       (default 0x403B0000 / 0x40400000)

import java.io.File;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.List;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.FlowType;


public class Mn103Dump extends GhidraScript {

    private static long envLong(String name, long fallback) {
        String v = System.getenv(name);
        if (v == null || v.trim().isEmpty()) {
            return fallback;
        }
        String t = v.trim();
        if (t.startsWith("0x") || t.startsWith("0X")) {
            t = t.substring(2);
        }
        return Long.parseLong(t, 16);
    }

    private String bytesOf(Instruction insn) throws Exception {
        byte[] b = insn.getBytes();
        StringBuilder sb = new StringBuilder();
        for (byte x : b) {
            sb.append(String.format("%02x", x & 0xff));
        }
        return sb.toString();
    }

    private String textOf(Instruction insn) {
        StringBuilder sb = new StringBuilder(insn.getMnemonicString());
        int n = insn.getNumOperands();
        for (int i = 0; i < n; i++) {
            sb.append(i == 0 ? " " : ", ");
            sb.append(insn.getDefaultOperandRepresentation(i));
        }
        return sb.toString();
    }

    @Override
    public void run() throws Exception {
        String outDir = getScriptArgs().length > 0 ? getScriptArgs()[0] : ".";

        long rangeStart = envLong("MN103_RANGE_START", 0x403B7965L);
        long rangeEnd = envLong("MN103_RANGE_END", 0x403B7A30L);
        long funcLo = envLong("MN103_FUNC_LO", 0x403B0000L);
        long funcHi = envLong("MN103_FUNC_HI", 0x40400000L);

        println("=== MN103Dump ===");
        println("language id        : " + currentProgram.getLanguageID().getIdAsString());
        println("compiler spec id   : " + currentProgram.getCompilerSpec().getCompilerSpecID().getIdAsString());
        println("address space size : "
            + currentProgram.getAddressFactory().getDefaultAddressSpace().getSize());
        println("image base         : " + currentProgram.getImageBase());
        println("program min/max    : " + currentProgram.getMinAddress() + " / " + currentProgram.getMaxAddress());

        MemoryBlock[] blocks = currentProgram.getMemory().getBlocks();
        for (MemoryBlock b : blocks) {
            println(String.format("block  %-10s %s - %s  (len 0x%x, init=%s)",
                b.getName(), b.getStart(), b.getEnd(), b.getSize(), b.isInitialized()));
        }

        // ---- 1. disassembly of the requested range -------------------------------
        Address start = toAddr(rangeStart);
        Address end = toAddr(rangeEnd);
        println("");
        println("=== DISASSEMBLY 0x" + Long.toHexString(rangeStart) + " .. 0x" + Long.toHexString(rangeEnd) + " ===");

        // If auto-analysis did not reach this area (e.g. -noanalysis runs), decode
        // it on demand so the range can still be compared with the objdump truth.
        InstructionIterator probe = currentProgram.getListing().getInstructions(start, true);
        if (!probe.hasNext()) {
            println("(range not yet decoded - running on-demand disassemble)");
            disassemble(start);
        }

        StringBuilder raw = new StringBuilder();
        int count = 0;
        int bad = 0;
        StringBuilder tsv = new StringBuilder();
        InstructionIterator it = currentProgram.getListing().getInstructions(start, true);
        while (it.hasNext()) {
            Instruction insn = it.next();
            if (insn.getAddress().getOffset() > rangeEnd) {
                break;
            }
            count++;
            String b = bytesOf(insn);
            // Ghidra renders an undecodable byte sequence with the mnemonic
            // "undefined"; anything else decoded cleanly.
            if ("undefined".equals(insn.getMnemonicString())) {
                bad++;
            }
            raw.append(b);
            String opnd = "";
            int nops = insn.getNumOperands();
            List<String> ops = new ArrayList<String>();
            for (int i = 0; i < nops; i++) {
                ops.add(insn.getDefaultOperandRepresentation(i));
            }
            opnd = String.join(", ", ops);
            tsv.append(String.format("%08x\t%s\t%s\t%s%n", insn.getAddress().getOffset(), b,
                insn.getMnemonicString(), opnd));
            println(String.format("%08x  %-20s %s", insn.getAddress().getOffset(), b, textOf(insn)));

            // show the p-code of CALL instructions (this is what the
            // cmdada mn103-call.patch changes)
            if (insn.getFlowType() != null && insn.getFlowType().isCall()) {
                println("    p-code for " + insn.getAddress() + ":");
                for (ghidra.program.model.pcode.PcodeOp op : insn.getPcode()) {
                    println("      " + op.toString());
                }
            }
        }
        File tsvFile = new File(outDir, "mn103-disasm.tsv");
        PrintWriter tsvw = new PrintWriter(tsvFile, "UTF-8");
        tsvw.write(tsv.toString());
        tsvw.close();
        println("wrote TSV disassembly to " + tsvFile.getAbsolutePath());
        println("");
        println("instructions in range : " + count);
        println("bad/undefined instrs  : " + bad);
        println("raw bytes (contiguous): " + raw);

        // ---- 2. functions inside the requested window ----------------------------
        println("");
        println("=== FUNCTIONS IN 0x" + Long.toHexString(funcLo) + " .. 0x" + Long.toHexString(funcHi) + " ===");
        FunctionIterator fit = currentProgram.getFunctionManager().getFunctions(toAddr(funcLo), true);
        int inRange = 0;
        while (fit.hasNext()) {
            Function f = fit.next();
            if (f.getEntryPoint().getOffset() > funcHi) {
                break;
            }
            inRange++;
            println(String.format("%08x  %-40s  bodyBytes=%d",
                f.getEntryPoint().getOffset(), f.getName(),
                f.getBody().getMaxAddress().getOffset() - f.getBody().getMinAddress().getOffset() + 1));
        }
        println("functions in range    : " + inRange);

        // ---- 3. total function count + full inventory ---------------------------
        int total = currentProgram.getFunctionManager().getFunctionCount();
        println("");
        println("=== TOTAL FUNCTIONS IN PROGRAM : " + total + " ===");

        File allFile = new File(outDir, "mn103-all-functions.txt");
        PrintWriter pw = new PrintWriter(allFile, "UTF-8");
        FunctionIterator all = currentProgram.getFunctionManager().getFunctions(true);
        int written = 0;
        List<String> perBlock = new ArrayList<>();
        for (MemoryBlock b : blocks) {
            perBlock.add(String.format("block %-10s functions=0", b.getName()));
        }
        while (all.hasNext()) {
            Function f = all.next();
            pw.println(String.format("%08x\t%s\t%d", f.getEntryPoint().getOffset(), f.getName(),
                f.getBody().getNumAddresses()));
            written++;
            MemoryBlock b = currentProgram.getMemory().getBlock(f.getEntryPoint());
            if (b != null) {
                for (int i = 0; i < blocks.length; i++) {
                    if (blocks[i].equals(b)) {
                        String s = perBlock.get(i);
                        int cur = Integer.parseInt(s.substring(s.lastIndexOf('=') + 1));
                        perBlock.set(i, String.format("block %-10s functions=%d", b.getName(), cur + 1));
                        break;
                    }
                }
            }
        }
        pw.close();
        println("wrote " + written + " functions to " + allFile.getAbsolutePath());

        println("");
        println("=== FUNCTION DISTRIBUTION BY BLOCK ===");
        for (String s : perBlock) {
            println(s);
        }
    }
}
