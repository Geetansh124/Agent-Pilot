/**
 * Tool Definitions & Function Declarations
 *
 * Formatted for both:
 * 1. OpenAI function calling schema (NVIDIA Chat Completions)
 * 2. Gemini Live API function declarations schema
 */

export const OPENAI_TOOLS = [
  {
    type: 'function',
    function: {
      name: 'calculator',
      description: 'Perform accurate mathematical and arithmetic calculations. Supports basic operators (+, -, *, /, %, ^) and scientific functions (sqrt, sin, cos, tan, log, abs, round, pi, e).',
      parameters: {
        type: 'object',
        properties: {
          expression: {
            type: 'string',
            description: 'The mathematical expression to evaluate, e.g. "(125 * 4) / 10 + sqrt(144)"',
          },
        },
        required: ['expression'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_current_datetime',
      description: 'Get the live current UTC date, time, weekday, year, and localized timestamp. Use whenever a query is time-sensitive or asks about today, this week, or current year.',
      parameters: {
        type: 'object',
        properties: {
          timezone: {
            type: 'string',
            description: 'IANA timezone name, e.g. "UTC", "America/New_York", "Asia/Kolkata", "Europe/London". Defaults to "UTC".',
          },
        },
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'web_search',
      description: 'Search the live web for recent information, news, documentation, or facts not present in model weights.',
      parameters: {
        type: 'object',
        properties: {
          query: {
            type: 'string',
            description: 'The search query to look up on the web.',
          },
        },
        required: ['query'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'fetch_web_url',
      description: 'Fetch and extract clean readable text or JSON from a public URL. Strips styling, navigation, and HTML boilerplate.',
      parameters: {
        type: 'object',
        properties: {
          url: {
            type: 'string',
            description: 'The public http or https web URL to scrape.',
          },
        },
        required: ['url'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_stock_price',
      description: 'Get live real-time stock quotes, day price changes, market status, and daily high/low for public equities.',
      parameters: {
        type: 'object',
        properties: {
          symbol: {
            type: 'string',
            description: 'Stock ticker symbol, e.g. "AAPL", "MSFT", "GOOGL", "NVDA", "TSLA".',
          },
        },
        required: ['symbol'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'analyze_tabular_data',
      description: 'Compute statistical metrics, distributions, column profiles, and row summaries for tabular CSV or JSON data.',
      parameters: {
        type: 'object',
        properties: {
          data: {
            type: 'string',
            description: 'CSV text or JSON array string representing tabular rows.',
          },
          question: {
            type: 'string',
            description: 'Optional specific question about the dataset.',
          },
        },
        required: ['data'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'rag_tool',
      description: 'Search through the attached document for the current thread to extract exact factual passages and citations.',
      parameters: {
        type: 'object',
        properties: {
          query: {
            type: 'string',
            description: 'Keywords or concept to search for in the attached document.',
          },
        },
        required: ['query'],
      },
    },
  },
];

/**
 * Gemini Live API function declarations schema
 */
export const GEMINI_FUNCTION_DECLARATIONS = [
  {
    name: 'calculator',
    description: 'Perform accurate mathematical and arithmetic calculations. Supports operators (+, -, *, /, %, ^) and math functions (sqrt, sin, cos, tan, log, abs, round, pi, e).',
    parameters: {
      type: 'OBJECT',
      properties: {
        expression: {
          type: 'STRING',
          description: 'The mathematical expression to evaluate, e.g. "(125 * 4) / 10 + sqrt(144)"',
        },
      },
      required: ['expression'],
    },
  },
  {
    name: 'get_current_datetime',
    description: 'Get the live current UTC date, time, weekday, year, and localized timestamp. Use whenever a query is time-sensitive or asks about today, this week, or current year.',
    parameters: {
      type: 'OBJECT',
      properties: {
        timezone: {
          type: 'STRING',
          description: 'IANA timezone name, e.g. "UTC", "America/New_York", "Asia/Kolkata", "Europe/London". Defaults to "UTC".',
        },
      },
    },
  },
  {
    name: 'web_search',
    description: 'Search the live web for recent information, news, documentation, or facts.',
    parameters: {
      type: 'OBJECT',
      properties: {
        query: {
          type: 'STRING',
          description: 'The search query to look up on the web.',
        },
      },
      required: ['query'],
    },
  },
  {
    name: 'fetch_web_url',
    description: 'Fetch and extract clean readable text or JSON from a public URL.',
    parameters: {
      type: 'OBJECT',
      properties: {
        url: {
          type: 'STRING',
          description: 'The public http or https web URL to scrape.',
        },
      },
      required: ['url'],
    },
  },
  {
    name: 'get_stock_price',
    description: 'Get live real-time stock quotes, day price changes, market status, and daily high/low for public equities.',
    parameters: {
      type: 'OBJECT',
      properties: {
        symbol: {
          type: 'STRING',
          description: 'Stock ticker symbol, e.g. "AAPL", "MSFT", "GOOGL", "NVDA", "TSLA".',
        },
      },
      required: ['symbol'],
    },
  },
  {
    name: 'analyze_tabular_data',
    description: 'Compute statistical metrics, distributions, column profiles, and row summaries for tabular CSV or JSON data.',
    parameters: {
      type: 'OBJECT',
      properties: {
        data: {
          type: 'STRING',
          description: 'CSV text or JSON array string representing tabular rows.',
        },
        question: {
          type: 'STRING',
          description: 'Optional question about the dataset.',
        },
      },
      required: ['data'],
    },
  },
  {
    name: 'rag_tool',
    description: 'Search through the attached document for the current thread to extract exact factual passages and citations.',
    parameters: {
      type: 'OBJECT',
      properties: {
        query: {
          type: 'STRING',
          description: 'Keywords or concept to search for in the attached document.',
        },
      },
      required: ['query'],
    },
  },
];
