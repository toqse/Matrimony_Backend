from decimal import Decimal

_ONES = ("Zero","One","Two","Three","Four","Five","Six","Seven","Eight","Nine","Ten","Eleven","Twelve","Thirteen","Fourteen","Fifteen","Sixteen","Seventeen","Eighteen","Nineteen")
_TENS = ("","","Twenty","Thirty","Forty","Fifty","Sixty","Seventy","Eighty","Ninety")

def _two(n):
    if n < 20: return _ONES[n]
    t,o = divmod(n,10)
    return _TENS[t] + (f' {_ONES[o]}' if o else '')

def _three(n):
    h, rest = divmod(n, 100)
    parts=[]
    if h: parts.append(f'{_ONES[h]} Hundred')
    if rest: parts.append(_two(rest))
    return ' '.join(parts)

def _int_indian(n):
    if n == 0: return 'Zero'
    parts=[]
    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thousand, n = divmod(n, 1_000)
    if crore: parts.append(f'{_int_indian(crore)} Crore')
    if lakh: parts.append(f'{_two(lakh)} Lakh')
    if thousand: parts.append(f'{_two(thousand)} Thousand')
    if n: parts.append(_three(n))
    return ' '.join(p for p in parts if p)

def words(a):
    d = Decimal(a or 0)
    if d < 0: return 'Minus ' + words(-d)
    r = int(d)
    p = int((d-r)*100)
    rw = _int_indian(r)
    if p: return f'{rw} Rupees and {_two(p)} Paise Only'
    return f'{rw} Rupees Only'

def fmt(a):
    d = Decimal(a or 0)
    sign = '-' if d < 0 else ''
    d = abs(d)
    w = int(d); p = int((d-w)*100)
    s = str(w)
    if len(s) <= 3: g = s
    else:
        last3, rest = s[-3:], s[:-3]
        ck=[]
        while len(rest)>2:
            ck.append(rest[-2:]); rest=rest[:-2]
        if rest: ck.append(rest)
        g = ','.join(reversed(ck)) + ',' + last3
    return f'{sign}Rs.{g}.{p:02d}'

for v in [0, 30000, 123456789.50, 1234.5, 100000, 99]:
    print(repr(v), '=>', fmt(v), '|', words(v))
