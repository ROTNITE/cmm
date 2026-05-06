# OmniRoute Setup Guide

## Quick Start

### 1. Get OmniRoute API Key

1. Start OmniRoute
2. Open http://localhost:20128/dashboard
3. Navigate to **Dashboard → API Manager**
4. Click **Create API Key** / **Add API Key** / **New Key**
5. Copy the key (format: `sk-...`)

### 2. Configure .env

Create or update `C:\cmm-main\.env`:

```bash
OMNIROUTE_API_KEY=sk-your-omniroute-key-here
OMNIROUTE_BASE_URL=http://localhost:20128/v1
AI_MODEL=kr/claude-sonnet-4.5
```

### 3. Verify Setup

```bash
curl http://localhost:20128/v1/models -H "Authorization: Bearer YOUR_OMNIROUTE_KEY"
```

Expected response: list of available models including `kr/claude-sonnet-4.5`.

### 4. Run Tests

```bash
python -m unittest discover -s tests
python main.py --query "Test query"
```

## Model Selection

- **kr/claude-sonnet-4.5** — faster, cheaper, recommended for agent testing
- **kr/claude-opus-4** — more capable, use for production or complex queries

## Fallback Priority

The system checks environment variables in this order:

1. `OMNIROUTE_API_KEY` / `OMNIROUTE_BASE_URL`
2. `CLAUDE_API_KEY` / `CLAUDE_BASE_URL`
3. `DEEPSEEK_API_KEY` / default DeepSeek URL
4. `OPENAI_API_KEY` / default OpenAI URL

This allows seamless switching between providers without code changes.

## Troubleshooting

### Connection refused
- Check OmniRoute is running: `curl http://localhost:20128/v1/models`
- Verify port 20128 is not blocked

### Invalid API key
- Regenerate key in OmniRoute dashboard
- Check `.env` file has no extra spaces or quotes around the key

### Model not found
- Verify model name matches OmniRoute's model list
- Use `curl http://localhost:20128/v1/models` to see available models
