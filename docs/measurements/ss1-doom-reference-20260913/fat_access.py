"""Read FAT16/32 without loop mounting; overwrite only preallocated file bytes."""
import struct
import sys

class Fat:
    def __init__(self, path, write=False):
        self.f = open(path, 'r+b' if write else 'rb')
        b = self.read(0, 512)
        self.ss = struct.unpack_from('<H', b, 11)[0]
        self.spc = b[13]
        reserved = struct.unpack_from('<H', b, 14)[0]
        nf = b[16]
        roots = struct.unpack_from('<H', b, 17)[0]
        fatsz = struct.unpack_from('<H', b, 22)[0]
        self.fat32 = fatsz == 0
        if self.fat32: fatsz = struct.unpack_from('<I', b, 36)[0]
        self.cs = self.ss * self.spc
        self.fat = self.read(reserved * self.ss, fatsz * self.ss)
        self.root_off = (reserved + nf * fatsz) * self.ss
        self.root_size = roots * 32
        self.data_off = self.root_off + ((self.root_size + self.ss-1)//self.ss)*self.ss
        self.root = struct.unpack_from('<I', b, 44)[0] if self.fat32 else 0
        assert self.ss == 512 and self.spc and self.spc & (self.spc-1) == 0

    def read(self, off, size):
        self.f.seek(off)
        b = self.f.read(size)
        assert len(b) == size, (off, size, len(b))
        return b

    def clusters(self, c):
        seen = set()
        while c >= 2 and c < (0x0ffffff8 if self.fat32 else 0xfff8):
            assert c not in seen, 'FAT chain loop'
            seen.add(c)
            yield self.data_off + (c-2)*self.cs
            c = struct.unpack_from('<I' if self.fat32 else '<H', self.fat, c*(4 if self.fat32 else 2))[0]
            if self.fat32: c &= 0x0fffffff

    def directory(self, cluster):
        data = b''.join(self.read(o, self.cs) for o in self.clusters(cluster)) if cluster else self.read(self.root_off, self.root_size)
        lfn = []
        for i in range(0, len(data), 32):
            e = data[i:i+32]
            if e[0] == 0: break
            if e[0] == 229: lfn = []; continue
            if e[11] == 15:
                text = (e[1:11]+e[14:26]+e[28:32]).decode('utf-16le').split('\0')[0].replace('\uffff', '')
                lfn.insert(0, text)
                continue
            short = e[:8].decode('latin1').rstrip() + ('.'+e[8:11].decode('latin1').rstrip() if e[8:11].strip() else '')
            name = ''.join(lfn) if lfn else short
            lfn = []
            if e[11] & 8: continue
            c = struct.unpack_from('<H', e, 26)[0] | (struct.unpack_from('<H', e, 20)[0]<<16 if self.fat32 else 0)
            yield name, c, struct.unpack_from('<I', e, 28)[0], bool(e[11]&16)

    def lookup(self, path):
        entry = ('/', self.root, 0, True)
        for part in path.strip('/').split('/'):
            if part:
                entry = next(e for e in self.directory(entry[1]) if e[0].lower() == part.lower())
        return entry

    def get(self, path):
        _, c, n, isdir = self.lookup(path)
        assert not isdir
        return b''.join(self.read(o, self.cs) for o in self.clusters(c))[:n]

    def put(self, path, data):
        _, c, n, isdir = self.lookup(path)
        assert not isdir and len(data) <= n
        data = data.ljust(n, b'\0')
        extents = []
        for off in self.clusters(c):
            if extents and extents[-1][0] + extents[-1][1] == off:
                extents[-1][1] += self.cs
            else: extents.append([off, self.cs])
        for off, size in extents:
            if not data: break
            self.f.seek(off)
            chunk, data = data[:size], data[size:]
            self.f.write(chunk)
        assert not data
        self.f.flush()

if __name__ == '__main__':
    mode, image, path = sys.argv[1:4]
    fat = Fat(image, mode == 'put')
    if mode == 'ls':
        for row in fat.directory(fat.lookup(path)[1]): print(*row)
    elif mode == 'get': sys.stdout.buffer.write(fat.get(path))
    elif mode == 'put': fat.put(path, sys.stdin.buffer.read())
