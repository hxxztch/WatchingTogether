"""Minimal test - check qwindows.dll integrity."""
import sys, os

# Check qwindows.dll BEFORE Qt initializes
_mei = getattr(sys, '_MEIPASS', None)
if _mei:
    _qp = os.path.join(_mei, "PySide6", "plugins", "platforms", "qwindows.dll")
    if os.path.exists(_qp):
        with open(_qp, "rb") as _f:
            _data = _f.read()
        # Write diagnostic to desktop
        _diag = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "file_check.txt")
        with open(_diag, "w") as _f2:
            _f2.write(f"qwindows.dll size: {len(_data)}\n")
            _f2.write(f"Original size: 890000\n")
            # Check first 2 bytes (MZ header)
            _f2.write(f"First 2 bytes: {hex(_data[0])} {hex(_data[1])}\n")
            # Check PE header
            import struct
            _pe_off = struct.unpack('<I', _data[0x3C:0x40])[0]
            _f2.write(f"PE offset: {hex(_pe_off)}\n")
            _f2.write(f"PE sig: {_data[_pe_off:_pe_off+4]}\n")
            # Check sections for .qtmetadata
            _num_sec = struct.unpack('<H', _data[_pe_off+6:_pe_off+8])[0]
            _f2.write(f"Sections: {_num_sec}\n")
            _opt_hdr = struct.unpack('<H', _data[_pe_off+20:_pe_off+22])[0]
            _sec_tbl = _pe_off + 24 + _opt_hdr
            for _i in range(_num_sec):
                _s = _sec_tbl + _i * 40
                _nm = _data[_s:_s+8].rstrip(b"\0").decode("ascii", errors="replace")
                _ro = struct.unpack('<I', _data[_s+20:_s+24])[0]
                _rs = struct.unpack('<I', _data[_s+16:_s+20])[0]
                if "qt" in _nm.lower():
                    _magic = _data[_ro:_ro+4]
                    _f2.write(f"  Section {_nm}: offset={hex(_ro)} size={_rs} magic={_magic}\n")

from PySide6.QtWidgets import QApplication, QLabel

def main():
    app = QApplication(sys.argv)
    label = QLabel("Test")
    label.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()