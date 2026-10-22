//Enable the auto-analysis analyzers that matter for a flat (header-less)
//MN103 firmware image.
//
//A raw image has no ELF headers and therefore no entry points, so Ghidra's
//stock auto-analysis finds no functions.  Two analyzers help:
//   "Aggressive Instruction Finder" - scans memory for code starts
//   "Decompiler Parameter ID"       - lets the decompiler find function starts
//
//Note: Ghidra 12.x has no analyzer literally named "Disassemble"; the bulk
//linear disassembly of a flat image is done by Mn103BulkAnalyze.java instead.

import ghidra.app.script.GhidraScript;

public class Mn103EnableDisassemble extends GhidraScript {

    @Override
    public void run() throws Exception {
        setAnalysisOption(currentProgram, "Aggressive Instruction Finder", "true");
        setAnalysisOption(currentProgram, "Decompiler Parameter ID", "true");
        println("[Mn103EnableDisassemble] Aggressive Instruction Finder  = true");
        println("[Mn103EnableDisassemble] Decompiler Parameter ID        = true");
        println("[Mn103EnableDisassemble] language = "
            + currentProgram.getLanguageID().getIdAsString()
            + "  cspec = " + currentProgram.getCompilerSpec().getCompilerSpecID().getIdAsString());
    }
}
