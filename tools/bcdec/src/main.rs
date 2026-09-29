//! Decode the block-compressed DDS files written by export_textures.py (BC1 / BC4 / BC5 / BC7,
//! or already-uncompressed BGRA) to uncompressed B8G8R8A8 DDS, which the Zone Kit's texture
//! importer accepts (it rejects compressed DDS).
//!
//!     bcdec <in root> <out root>        converts every .dds under <in root>, mirroring paths
mod tables;

use std::fs;
use std::path::{Path, PathBuf};

#[derive(Clone, Copy, PartialEq, Debug)]
enum Fmt { Bc1, Bc4, Bc5, Bc7, Bgra }

fn u32le(d: &[u8], o: usize) -> u32 { u32::from_le_bytes([d[o], d[o + 1], d[o + 2], d[o + 3]]) }

fn parse_header(d: &[u8]) -> Result<(Fmt, usize, usize, usize), String> {
    if &d[0..4] != b"DDS " { return Err("not a DDS".into()); }
    let h = u32le(d, 12) as usize;
    let w = u32le(d, 16) as usize;
    let pf_flags = u32le(d, 80);
    let fourcc = &d[84..88];
    if fourcc == b"DXT1" { return Ok((Fmt::Bc1, w, h, 128)); }
    if fourcc == b"DX10" {
        let dxgi = u32le(d, 128);
        let f = match dxgi { 80 => Fmt::Bc4, 83 => Fmt::Bc5, 98 => Fmt::Bc7, 87 => Fmt::Bgra, x => return Err(format!("dxgi {}", x)) };
        return Ok((f, w, h, 148));
    }
    if pf_flags & 0x40 != 0 && u32le(d, 88) == 32 { return Ok((Fmt::Bgra, w, h, 128)); }
    Err(format!("unsupported pixel format flags {:#x}", pf_flags))
}

fn rgb565(c: u16) -> [u8; 3] {
    let r = ((c >> 11) & 31) as u32; let g = ((c >> 5) & 63) as u32; let b = (c & 31) as u32;
    [((r * 527 + 23) >> 6) as u8, ((g * 259 + 33) >> 6) as u8, ((b * 527 + 23) >> 6) as u8]
}

fn bc1(b: &[u8], out: &mut [[u8; 4]; 16]) {
    let c0 = u16::from_le_bytes([b[0], b[1]]); let c1 = u16::from_le_bytes([b[2], b[3]]);
    let (a, bb) = (rgb565(c0), rgb565(c1));
    let mut pal = [[0u8; 4]; 4];
    pal[0] = [a[0], a[1], a[2], 255]; pal[1] = [bb[0], bb[1], bb[2], 255];
    if c0 > c1 {
        for i in 0..3 {
            pal[2][i] = ((2 * a[i] as u32 + bb[i] as u32) / 3) as u8;
            pal[3][i] = ((a[i] as u32 + 2 * bb[i] as u32) / 3) as u8;
        }
        pal[2][3] = 255; pal[3][3] = 255;
    } else {
        for i in 0..3 { pal[2][i] = ((a[i] as u32 + bb[i] as u32) / 2) as u8; }
        pal[2][3] = 255; pal[3] = [0, 0, 0, 0];
    }
    let bits = u32le(b, 4);
    for i in 0..16 { out[i] = pal[((bits >> (2 * i)) & 3) as usize]; }
}

fn bc4(b: &[u8]) -> [u8; 16] {
    let (a0, a1) = (b[0] as u32, b[1] as u32);
    let mut pal = [0u32; 8];
    pal[0] = a0; pal[1] = a1;
    if a0 > a1 {
        for i in 1..7 { pal[i + 1] = ((7 - i as u32) * a0 + i as u32 * a1) / 7; }
    } else {
        for i in 1..5 { pal[i + 1] = ((5 - i as u32) * a0 + i as u32 * a1) / 5; }
        pal[6] = 0; pal[7] = 255;
    }
    let mut bits: u64 = 0;
    for i in 0..6 { bits |= (b[2 + i] as u64) << (8 * i); }
    let mut out = [0u8; 16];
    for i in 0..16 { out[i] = pal[((bits >> (3 * i)) & 7) as usize] as u8; }
    out
}

struct Bits { v: u128, pos: u32 }
impl Bits {
    fn take(&mut self, n: u32) -> u32 {
        if n == 0 { return 0; }
        let r = ((self.v >> self.pos) & ((1u128 << n) - 1)) as u32;
        self.pos += n; r
    }
}

const W2: [u32; 4] = [0, 21, 43, 64];
const W3: [u32; 8] = [0, 9, 18, 27, 37, 46, 55, 64];
const W4: [u32; 16] = [0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64];

fn weights(bits: u32) -> &'static [u32] { match bits { 2 => &W2, 3 => &W3, _ => &W4 } }
fn interp(e0: u32, e1: u32, w: u32) -> u8 { (((64 - w) * e0 + w * e1 + 32) >> 6) as u8 }
fn expand(v: u32, bits: u32) -> u32 { let v = v << (8 - bits); v | (v >> bits) }

// mode: (subsets, partition bits, rotation bits, index-selection bits, color bits, alpha bits, endpoint pbits, shared pbits, index bits, index2 bits)
const MODES: [(usize, u32, u32, u32, u32, u32, u32, u32, u32, u32); 8] = [
    (3, 4, 0, 0, 4, 0, 1, 0, 3, 0),
    (2, 6, 0, 0, 6, 0, 0, 1, 3, 0),
    (3, 6, 0, 0, 5, 0, 0, 0, 2, 0),
    (2, 6, 0, 0, 7, 0, 1, 0, 2, 0),
    (1, 0, 2, 1, 5, 6, 0, 0, 2, 3),
    (1, 0, 2, 0, 7, 8, 0, 0, 2, 2),
    (1, 0, 0, 0, 7, 7, 1, 0, 4, 0),
    (2, 6, 0, 0, 5, 5, 1, 0, 2, 0),
];

fn bc7(b: &[u8], out: &mut [[u8; 4]; 16]) {
    let mut v: u128 = 0;
    for i in 0..16 { v |= (b[i] as u128) << (8 * i); }
    let mut s = Bits { v, pos: 0 };
    let mut mode = 0usize;
    while mode < 8 && s.take(1) == 0 { mode += 1; }
    if mode == 8 { *out = [[0, 0, 0, 0]; 16]; return; }
    let (ns, pb, rb, isb, cb, ab, epb, spb, ib, ib2) = MODES[mode];
    let part = s.take(pb) as usize;
    let rot = s.take(rb);
    let isel = s.take(isb);
    let mut ep = [[0u32; 4]; 6];
    for c in 0..3 { for e in 0..2 * ns { ep[e][c] = s.take(cb); } }
    if ab > 0 { for e in 0..2 * ns { ep[e][3] = s.take(ab); } }
    let (mut cbits, mut abits) = (cb, ab);
    if epb > 0 {
        for e in 0..2 * ns { let p = s.take(1); for c in 0..4 { ep[e][c] = (ep[e][c] << 1) | p; } }
        cbits += 1; if ab > 0 { abits += 1; }
    }
    if spb > 0 {
        for sub in 0..ns { let p = s.take(1); for e in 0..2 { for c in 0..4 { ep[sub * 2 + e][c] = (ep[sub * 2 + e][c] << 1) | p; } } }
        cbits += 1; if ab > 0 { abits += 1; }
    }
    for e in 0..2 * ns {
        for c in 0..3 { ep[e][c] = expand(ep[e][c], cbits); }
        ep[e][3] = if ab > 0 { expand(ep[e][3], abits) } else { 255 };
    }
    let ptab = &tables::PARTITION[ns - 1][part];
    let fix = &tables::FIXUP[ns - 1][part];
    let is_anchor = |i: usize| -> bool { i == 0 || (ns >= 2 && i == fix[1] as usize) || (ns == 3 && i == fix[2] as usize) };
    let mut idx = [0u32; 16];
    for i in 0..16 { idx[i] = s.take(if is_anchor(i) { ib - 1 } else { ib }); }
    let mut idx2 = [0u32; 16];
    if ib2 > 0 { for i in 0..16 { idx2[i] = s.take(if i == 0 { ib2 - 1 } else { ib2 }); } }
    for i in 0..16 {
        let sub = ptab[i] as usize;
        let (e0, e1) = (ep[sub * 2], ep[sub * 2 + 1]);
        let mut px = [0u8; 4];
        if ib2 > 0 {
            let (ci, cw, ai, aw) = if isel == 0 { (idx[i], ib, idx2[i], ib2) } else { (idx2[i], ib2, idx[i], ib) };
            let wc = weights(cw)[ci as usize]; let wa = weights(aw)[ai as usize];
            for c in 0..3 { px[c] = interp(e0[c], e1[c], wc); }
            px[3] = interp(e0[3], e1[3], wa);
        } else {
            let w = weights(ib)[idx[i] as usize];
            for c in 0..4 { px[c] = interp(e0[c], e1[c], w); }
        }
        match rot { 1 => px.swap(0, 3), 2 => px.swap(1, 3), 3 => px.swap(2, 3), _ => {} }
        out[i] = px;
    }
}

fn decode(d: &[u8]) -> Result<(usize, usize, Vec<u8>), String> {
    let (f, w, h, off) = parse_header(d)?;
    let data = &d[off..];
    let mut bgra = vec![0u8; w * h * 4];
    if f == Fmt::Bgra {
        if data.len() < w * h * 4 { return Err("short BGRA data".into()); }
        bgra.copy_from_slice(&data[..w * h * 4]);
        return Ok((w, h, bgra));
    }
    let (bw, bh) = ((w + 3) / 4, (h + 3) / 4);
    let bsize = if f == Fmt::Bc1 || f == Fmt::Bc4 { 8 } else { 16 };
    if data.len() < bw * bh * bsize { return Err(format!("short block data {} < {}", data.len(), bw * bh * bsize)); }
    let mut px = [[0u8; 4]; 16];
    for by in 0..bh {
        for bx in 0..bw {
            let blk = &data[(by * bw + bx) * bsize..][..bsize];
            match f {
                Fmt::Bc1 => bc1(blk, &mut px),
                Fmt::Bc7 => bc7(blk, &mut px),
                Fmt::Bc4 => { let r = bc4(blk); for i in 0..16 { px[i] = [r[i], r[i], r[i], 255]; } }
                Fmt::Bc5 => {
                    let r = bc4(&blk[..8]); let g = bc4(&blk[8..]);
                    for i in 0..16 {
                        let x = r[i] as f32 / 127.5 - 1.0; let y = g[i] as f32 / 127.5 - 1.0;
                        let z = (1.0 - x * x - y * y).max(0.0).sqrt();
                        px[i] = [r[i], g[i], ((z * 0.5 + 0.5) * 255.0).round() as u8, 255];
                    }
                }
                Fmt::Bgra => unreachable!(),
            }
            for i in 0..16 {
                let (x, y) = (bx * 4 + (i & 3), by * 4 + (i >> 2));
                if x >= w || y >= h { continue; }
                let o = (y * w + x) * 4;
                let p = px[i];
                bgra[o] = p[2]; bgra[o + 1] = p[1]; bgra[o + 2] = p[0]; bgra[o + 3] = p[3];
            }
        }
    }
    Ok((w, h, bgra))
}

fn write_bgra_dds(path: &Path, w: usize, h: usize, px: &[u8]) -> std::io::Result<()> {
    let mut hd = Vec::with_capacity(128 + px.len());
    hd.extend_from_slice(b"DDS ");
    for v in [124u32, 0x1 | 0x2 | 0x4 | 0x1000 | 0x8, h as u32, w as u32, (w * 4) as u32, 0, 1] { hd.extend_from_slice(&v.to_le_bytes()); }
    hd.extend_from_slice(&[0u8; 44]);
    for v in [32u32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000] { hd.extend_from_slice(&v.to_le_bytes()); }
    for v in [0x1000u32, 0, 0, 0, 0] { hd.extend_from_slice(&v.to_le_bytes()); }
    hd.extend_from_slice(px);
    fs::write(path, hd)
}

fn walk(dir: &Path, out: &mut Vec<PathBuf>) {
    if let Ok(rd) = fs::read_dir(dir) {
        for e in rd.flatten() {
            let p = e.path();
            if p.is_dir() { walk(&p, out); } else if p.extension().map(|x| x == "dds").unwrap_or(false) { out.push(p); }
        }
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 { eprintln!("usage: bcdec <in root> <out root>"); std::process::exit(2); }
    let (src, dst) = (Path::new(&args[1]), Path::new(&args[2]));
    let mut files = Vec::new();
    walk(src, &mut files);
    files.sort();
    let (mut ok, mut bad) = (0, 0);
    for f in &files {
        let rel = f.strip_prefix(src).unwrap();
        let out = dst.join(rel);
        let res = fs::read(f).map_err(|e| e.to_string()).and_then(|d| decode(&d)).and_then(|(w, h, px)| {
            fs::create_dir_all(out.parent().unwrap()).map_err(|e| e.to_string())?;
            write_bgra_dds(&out, w, h, &px).map_err(|e| e.to_string())
        });
        match res { Ok(()) => ok += 1, Err(e) => { bad += 1; eprintln!("FAIL {}: {}", rel.display(), e); } }
    }
    println!("decoded {}, failed {}", ok, bad);
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn tables_sane() {
        assert_eq!(tables::PARTITION[1][0], [0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1]);
        assert_eq!(tables::FIXUP[1][0][1], 15);
        assert_eq!(tables::FIXUP[2][0], [0, 3, 15]);
    }
    #[test]
    fn bc7_mode6_solid() {
        // mode 6, all endpoints 0x7F with pbit 1 -> 255, indices 0 -> white opaque
        let mut v: u128 = 1 << 6;                  // mode 6
        let mut pos = 7;
        for _ in 0..8 { v |= 0x7Fu128 << pos; pos += 7; }   // R0 R1 G0 G1 B0 B1 A0 A1
        v |= 1u128 << pos; pos += 1; v |= 1u128 << pos;     // pbits
        let b = v.to_le_bytes();
        let mut px = [[0u8; 4]; 16];
        bc7(&b, &mut px);
        assert_eq!(px[0], [255, 255, 255, 255]);
        assert_eq!(px[15], [255, 255, 255, 255]);
    }
}
