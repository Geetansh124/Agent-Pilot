/**
 * Safe Mathematical Expression Calculator
 * Evaluates expressions without eval() or Function().
 */

export function calculateExpression(expr: string): { success: boolean; result?: number | string; error?: string } {
  try {
    const sanitized = expr.replace(/\s+/g, '');
    if (!sanitized) {
      return { success: false, error: 'Empty expression' };
    }

    // Tokenize
    const tokens: string[] = [];
    let i = 0;
    while (i < sanitized.length) {
      const char = sanitized[i];
      if ('+-*/%^()'.includes(char)) {
        tokens.push(char);
        i++;
      } else if (/\d/.test(char) || char === '.') {
        let numStr = '';
        while (i < sanitized.length && (/\d/.test(sanitized[i]) || sanitized[i] === '.')) {
          numStr += sanitized[i];
          i++;
        }
        tokens.push(numStr);
      } else if (/[a-zA-Z]/.test(char)) {
        let funcName = '';
        while (i < sanitized.length && /[a-zA-Z0-9]/.test(sanitized[i])) {
          funcName += sanitized[i];
          i++;
        }
        tokens.push(funcName.toLowerCase());
      } else {
        return { success: false, error: `Invalid character: ${char}` };
      }
    }

    let pos = 0;
    const peek = (): string | undefined => tokens[pos];
    const consume = (): string => tokens[pos++];

    function parseExpression(): number {
      let value = parseTerm();
      while (peek() === '+' || peek() === '-') {
        const op = consume();
        const nextTerm = parseTerm();
        if (op === '+') value += nextTerm;
        if (op === '-') value -= nextTerm;
      }
      return value;
    }

    function parseTerm(): number {
      let value = parseFactor();
      while (peek() === '*' || peek() === '/' || peek() === '%') {
        const op = consume();
        const nextFactor = parseFactor();
        if (op === '*') value *= nextFactor;
        if (op === '/') {
          if (nextFactor === 0) throw new Error('Division by zero');
          value /= nextFactor;
        }
        if (op === '%') value %= nextFactor;
      }
      return value;
    }

    function parseFactor(): number {
      let value = parsePrimary();
      while (peek() === '^') {
        consume();
        const nextPower = parseFactor();
        value = Math.pow(value, nextPower);
      }
      return value;
    }

    function parsePrimary(): number {
      const t = peek();
      if (!t) throw new Error('Unexpected end of expression');

      if (t === '+') {
        consume();
        return parsePrimary();
      }
      if (t === '-') {
        consume();
        return -parsePrimary();
      }

      if (t === '(') {
        consume();
        const value = parseExpression();
        if (peek() !== ')') throw new Error("Missing closing ')'");
        consume();
        return value;
      }

      if (t === 'pi') {
        consume();
        return Math.PI;
      }
      if (t === 'e') {
        consume();
        return Math.E;
      }

      const mathFuncs: Record<string, (x: number) => number> = {
        sqrt: Math.sqrt,
        cbrt: Math.cbrt,
        sin: (x) => Math.sin((x * Math.PI) / 180),
        cos: (x) => Math.cos((x * Math.PI) / 180),
        tan: (x) => Math.tan((x * Math.PI) / 180),
        abs: Math.abs,
        log: Math.log,
        log10: Math.log10,
        exp: Math.exp,
        round: Math.round,
        floor: Math.floor,
        ceil: Math.ceil,
      };

      if (mathFuncs[t]) {
        const fn = mathFuncs[t];
        consume();
        if (peek() !== '(') throw new Error(`Expected '(' after function ${t}`);
        consume();
        const arg = parseExpression();
        if (peek() !== ')') throw new Error(`Missing closing ')' for function ${t}`);
        consume();
        return fn(arg);
      }

      const num = parseFloat(t);
      if (isNaN(num)) {
        throw new Error(`Unknown token: ${t}`);
      }
      consume();
      return num;
    }

    const val = parseExpression();
    if (pos < tokens.length) {
      throw new Error(`Unexpected trailing token: ${tokens[pos]}`);
    }

    const rounded = Math.abs(val - Math.round(val)) < 1e-12 ? Math.round(val) : Number(val.toFixed(8));
    return { success: true, result: rounded };
  } catch (err: any) {
    return { success: false, error: err.message || 'Calculation error' };
  }
}
