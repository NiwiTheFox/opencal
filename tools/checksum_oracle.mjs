// Development-only oracle, Node 24+ with --experimental-transform-types.
// GPL-3.0-only. Original upstream module retained, not rewritten for this check.
// Run: node --experimental-transform-types tools/checksum_oracle.mjs FILE.bin
import fs from 'node:fs';
import crypto from 'node:crypto';
import {correctEDC15PChecksum} from '../third_party/zedsuite/src/lib/ecu/bosch/checksums/edc15p-checksum.ts';
const path=process.argv[2];
if (!path) throw new Error('Supply a BIN path. The input is read-only.');
const original=fs.readFileSync(path);
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const results=[];
for (const offset of [0x8001,0x10011,0x4a000,0x6c900]) {
  if(offset>=original.length) throw new Error('BIN too small for these vectors.');
  const copy=Buffer.from(original); copy[offset]^=1;
  const {info,correctedData}=correctEDC15PChecksum([...copy]);
  results.push({offset,info,corrected_sha256:sha(Buffer.from(correctedData))});
}
console.log(JSON.stringify({original_sha256:sha(original),mutations:results},null,2));
