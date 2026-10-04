/**
 * Agent-Pilot Edge Tools Suite
 * Unified entry point and execution engine for all edge tools.
 */

import { calculateExpression } from './calculator';
import { getCurrentDateTime } from './temporal';
import { fetchWebUrl, webSearch, getStockPrice } from './web';
import { analyzeTabularData } from './tabular';

export { calculateExpression } from './calculator';
export { getCurrentDateTime } from './temporal';
export { fetchWebUrl, webSearch, getStockPrice } from './web';
export { analyzeTabularData } from './tabular';

export interface ToolResult {
  success: boolean;
  tool: string;
  result: any;
  error?: string;
}

/**
 * Unified Edge Tool Dispatcher
 */
export async function executeEdgeTool(
  toolName: string,
  args: Record<string, any>,
  context?: { db?: any; threadId?: string }
): Promise<ToolResult> {
  const name = toolName.toLowerCase().trim();

  try {
    switch (name) {
      case 'calculator':
        return {
          success: true,
          tool: name,
          result: calculateExpression(String(args.expression || '')),
        };

      case 'get_current_datetime':
        return {
          success: true,
          tool: name,
          result: getCurrentDateTime(String(args.timezone || 'UTC')),
        };

      case 'fetch_web_url':
        return {
          success: true,
          tool: name,
          result: await fetchWebUrl(String(args.url || '')),
        };

      case 'web_search':
        return {
          success: true,
          tool: name,
          result: await webSearch(String(args.query || '')),
        };

      case 'get_stock_price':
        return {
          success: true,
          tool: name,
          result: await getStockPrice(String(args.symbol || '')),
        };

      case 'analyze_tabular_data':
        return {
          success: true,
          tool: name,
          result: analyzeTabularData(String(args.data || '')),
        };

      case 'rag_tool': {
        const query = String(args.query || '');
        if (!context?.db || !context?.threadId) {
          return {
            success: true,
            tool: name,
            result: { message: 'Document search context unavailable for thread.', matches: [] },
          };
        }

        const docRes = await context.db
          .prepare(
            `SELECT d.filename, d.text_content
             FROM threads t
             JOIN documents d ON t.active_document_id = d.id
             WHERE t.id = ? LIMIT 1`
          )
          .bind(context.threadId)
          .first();

        if (!docRes || !docRes.text_content) {
          return {
            success: true,
            tool: name,
            result: { message: 'No document attached to current thread.', matches: [] },
          };
        }

        const text = String(docRes.text_content);
        const queryTerms = query.toLowerCase().split(/\s+/).filter((w) => w.length > 2);
        const paragraphs = text.split(/\n\n+/);
        const matchedParagraphs = paragraphs
          .map((p) => {
            const lower = p.toLowerCase();
            const score = queryTerms.reduce((acc, term) => acc + (lower.includes(term) ? 1 : 0), 0);
            return { text: p.trim(), score };
          })
          .filter((p) => p.score > 0)
          .sort((a, b) => b.score - a.score)
          .slice(0, 3)
          .map((p) => p.text);

        return {
          success: true,
          tool: name,
          result: {
            filename: docRes.filename,
            matches: matchedParagraphs.length > 0 ? matchedParagraphs : [text.slice(0, 1500)],
          },
        };
      }

      default:
        return {
          success: false,
          tool: name,
          result: null,
          error: `Tool '${toolName}' not found in edge toolset.`,
        };
    }
  } catch (err: any) {
    return {
      success: false,
      tool: name,
      result: null,
      error: err.message || 'Execution failed',
    };
  }
}
