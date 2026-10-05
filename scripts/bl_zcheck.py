import bpy
exec(open("/private/tmp/claude-501/-Users-dan-WishCaptury/a6354438-d500-490d-9fcf-d1a74f5f98d2/scratchpad/zfix.py").read().replace("ZF_PAIRS, ZF_VICTIMS = zf_cure()", ""))
objs = [o for o in bpy.data.objects if o.type == "MESH" and not o.name.startswith(ZF_SKIP)]
left = zf_pairs(objs)
print("ZCHECK remaining pairs", len(left), flush=True)
import collections
c = collections.Counter(tuple(sorted(x.rstrip("0123456789_.") for x in p)) for p in left)
for k, v in c.most_common(40): print("ZLEFT", v, k, flush=True)
