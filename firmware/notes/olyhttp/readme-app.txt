Hello, I've done some hacking on the olympus usb firmware update protocol: http://linda.karlov.mff.cuni.cz/~jove/oly/

I've made my own fake update server in python (oly_http.py) and captured the usb communication from update tool in virtualbox windows with wireshark (update.usb.dump, use filter: (scsi.sbc.opcode >= 0xc0 || scsi.spc.opcode >= 0xc0) && !(scsi.status == 0x00)). Protocol dissection is in proto.odt. Custom scsi commands are used, sg3_utils package can be used to send those. oly_scsi.py handles initial reads (serial no. and other info) and works ok. I didn't attempt yet to do the writes, since there are still some open questions.

Let me know if there is interest in more info.

jove
