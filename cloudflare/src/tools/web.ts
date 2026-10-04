/**
 * Web Scraping, Search, and Financial Market Tools
 */

export async function fetchWebUrl(targetUrl: string): Promise<Record<string, any>> {
  try {
    const parsed = new URL(targetUrl);
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      return { error: 'Invalid URL protocol. Must be http: or https:' };
    }

    const res = await fetch(parsed.toString(), {
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; AgentPilotEdge/2.0; +https://agent-pilot.soapy-pint.workers.dev)',
        'Accept': 'text/html,application/xhtml+xml,application/json,text/plain;q=0.9',
      },
    });

    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      const jsonData = await res.json();
      return {
        url: targetUrl,
        status: res.status,
        type: 'json',
        data: jsonData,
      };
    }

    const html = await res.text();
    const titleMatch = html.match(/<title[^>]*>([^<]*)<\/title>/i);
    const title = titleMatch ? titleMatch[1].trim() : '';

    const cleaned = html
      .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, ' ')
      .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, ' ')
      .replace(/<svg\b[^<]*(?:(?!<\/svg>)<[^<]*)*<\/svg>/gi, ' ')
      .replace(/<noscript\b[^<]*(?:(?!<\/noscript>)<[^<]*)*<\/noscript>/gi, ' ')
      .replace(/<[^>]+>/g, ' ')
      .replace(/&nbsp;/g, ' ')
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/\s+/g, ' ')
      .trim();

    return {
      url: targetUrl,
      status: res.status,
      title,
      content: cleaned.slice(0, 3500),
      total_characters: cleaned.length,
    };
  } catch (err: any) {
    return { error: `Failed to fetch URL: ${err.message}` };
  }
}

export async function webSearch(query: string): Promise<Record<string, any>> {
  try {
    const trimmed = query.trim();
    if (!trimmed) return { error: 'Empty search query' };

    const searchUrl = `https://html.duckduckgo.com/html/?q=${encodeURIComponent(trimmed)}`;
    const res = await fetch(searchUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      },
    });

    if (!res.ok) {
      return { query: trimmed, results: [], message: `Search upstream returned HTTP ${res.status}` };
    }

    const html = await res.text();
    const results: Array<{ title: string; link: string; snippet: string }> = [];

    const resultBlocks = html.split('<div class="result results_links');
    for (const block of resultBlocks.slice(1, 6)) {
      const linkMatch = block.match(/<a class="result__url[^>]*href="([^"]*)"/i) ||
                        block.match(/href="\/\/duckduckgo\.com\/l\/\?uddg=([^&"]+)/i);
      const snippetMatch = block.match(/<a class="result__snippet[^>]*>([\s\S]*?)<\/a>/i);

      let title = '';
      const anchorTitleMatch = block.match(/<a class="result__a"[^>]*>([\s\S]*?)<\/a>/i);
      if (anchorTitleMatch) {
        title = anchorTitleMatch[1].replace(/<[^>]+>/g, '').trim();
      }

      let link = '';
      if (linkMatch) {
        const rawLink = linkMatch[1];
        if (rawLink.startsWith('http')) {
          link = rawLink;
        } else {
          try {
            link = decodeURIComponent(rawLink);
          } catch {
            link = rawLink;
          }
        }
      }

      let snippet = '';
      if (snippetMatch) {
        snippet = snippetMatch[1].replace(/<[^>]+>/g, '').trim();
      }

      if (title || snippet) {
        results.push({
          title: title || 'Search Result',
          link: link || 'https://duckduckgo.com',
          snippet: snippet || '',
        });
      }
    }

    return {
      query: trimmed,
      total_found: results.length,
      results,
    };
  } catch (err: any) {
    return { error: `Web search failed: ${err.message}`, query };
  }
}

export async function getStockPrice(symbol: string): Promise<Record<string, any>> {
  try {
    const cleanSym = symbol.trim().toUpperCase().replace(/[^A-Z0-9.-]/g, '');
    if (!cleanSym) return { error: 'Invalid stock symbol' };

    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(cleanSym)}?interval=1d&range=5d`;
    const res = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
      },
    });

    if (!res.ok) {
      return { error: `Stock lookup failed with status ${res.status}`, symbol: cleanSym };
    }

    const data = await res.json() as any;
    const meta = data?.chart?.result?.[0]?.meta;
    if (!meta) {
      return { error: `No market data available for ticker ${cleanSym}`, symbol: cleanSym };
    }

    const price = meta.regularMarketPrice ?? meta.chartPreviousClose ?? 0;
    const prevClose = meta.chartPreviousClose ?? price;
    const change = Number((price - prevClose).toFixed(2));
    const percentChange = prevClose !== 0 ? Number(((change / prevClose) * 100).toFixed(2)) : 0;

    return {
      symbol: cleanSym,
      currency: meta.currency || 'USD',
      current_price: price,
      previous_close: prevClose,
      change,
      percent_change: percentChange,
      regular_market_day_high: meta.regularMarketDayHigh || null,
      regular_market_day_low: meta.regularMarketDayLow || null,
      exchange: meta.exchangeName || 'Unknown',
      market_state: change >= 0 ? 'up' : 'down',
    };
  } catch (err: any) {
    return { error: `Stock price lookup error: ${err.message}`, symbol };
  }
}
