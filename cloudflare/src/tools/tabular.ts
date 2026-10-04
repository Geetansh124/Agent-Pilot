/**
 * Tabular Data Profiler (CSV & JSON Analysis)
 */

export function analyzeTabularData(data: string): Record<string, any> {
  try {
    const raw = data.trim();
    if (!raw) return { error: 'Tabular data cannot be empty' };

    let rows: Array<Record<string, any>> = [];

    if (raw.startsWith('[') || raw.startsWith('{')) {
      try {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          rows = parsed.filter((item) => typeof item === 'object' && item !== null);
        } else if (typeof parsed === 'object') {
          rows = [parsed];
        }
      } catch (err: any) {
        return { error: `Invalid JSON tabular data: ${err.message}` };
      }
    } else {
      const lines = raw.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
      if (lines.length < 2) {
        return { error: 'CSV requires at least 1 header line and 1 data row.' };
      }

      const headers = lines[0].split(',').map((h) => h.replace(/^["']|["']$/g, '').trim());
      for (const line of lines.slice(1)) {
        const values = line.split(',').map((v) => v.replace(/^["']|["']$/g, '').trim());
        const rowObj: Record<string, any> = {};
        headers.forEach((h, idx) => {
          rowObj[h] = values[idx] !== undefined ? values[idx] : null;
        });
        rows.push(rowObj);
      }
    }

    if (!rows.length) {
      return { error: 'No data rows extracted from tabular input.' };
    }

    const columns = Object.keys(rows[0]);
    const summary: Record<string, any> = {};

    for (const col of columns) {
      const values = rows.map((r) => r[col]).filter((v) => v !== null && v !== undefined && v !== '');
      const numVals = values.map((v) => Number(v)).filter((n) => !isNaN(n));

      if (numVals.length > 0 && numVals.length === values.length) {
        const sum = numVals.reduce((a, b) => a + b, 0);
        const min = Math.min(...numVals);
        const max = Math.max(...numVals);
        const avg = Number((sum / numVals.length).toFixed(2));
        summary[col] = {
          type: 'numeric',
          count: numVals.length,
          min,
          max,
          avg,
          sum: Number(sum.toFixed(2)),
        };
      } else {
        const uniqueSet = new Set(values.map(String));
        summary[col] = {
          type: 'categorical',
          count: values.length,
          unique_values: uniqueSet.size,
          sample_values: Array.from(uniqueSet).slice(0, 5),
        };
      }
    }

    return {
      total_rows: rows.length,
      total_columns: columns.length,
      columns,
      summary,
      preview: rows.slice(0, 3),
    };
  } catch (err: any) {
    return { error: `Tabular analysis failed: ${err.message}` };
  }
}
