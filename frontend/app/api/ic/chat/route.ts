import { NextRequest, NextResponse } from "next/server";
import { checkPii, formatPiiWarning } from "@/lib/pii";

// Policy structure for type safety
interface Policy {
  investor_profile?: {
    investor_type?: string;
    base_currency?: string;
    portfolio_value?: number;
  };
  risk_appetite?: {
    risk_tolerance?: string;
    max_volatility?: number;
    max_drawdown?: number;
    time_horizon?: string;
    liquidity_needs?: number;
  };
  constraints?: {
    min_equity?: number;
    max_equity?: number;
    min_fixed_income?: number;
    max_fixed_income?: number;
    min_cash?: number;
    max_cash?: number;
    max_single_position?: number;
    max_sector_exposure?: number;
    min_positions?: number;
  };
  preferences?: {
    esg_focus?: boolean;
    exclusions?: string[];
    preferred_themes?: string[];
    factor_tilts?: Record<string, number>;
    home_bias?: number;
  };
  benchmark_settings?: {
    benchmark?: string;
    target_return?: number;
    rebalance_frequency?: string;
    rebalance_threshold?: number;
  };
}

interface ChatResponse {
  response: string;
  policy: Policy;
  updates: string[];
  missingFields?: string[];
  readyToLaunch?: boolean;
}

/**
 * Check policy completeness and return missing crucial fields
 */
function checkPolicyCompleteness(policy: Policy): { ready: boolean; missing: string[] } {
  const missing: string[] = [];

  // Crucial fields that must be set
  if (!policy.risk_appetite?.risk_tolerance) {
    missing.push("risk tolerance (conservative, moderate, or aggressive)");
  }
  if (!policy.investor_profile?.portfolio_value || policy.investor_profile.portfolio_value < 1000) {
    missing.push("portfolio value");
  }
  if (!policy.risk_appetite?.time_horizon) {
    missing.push("investment time horizon");
  }

  return {
    ready: missing.length === 0,
    missing,
  };
}

/**
 * Generate a follow-up question for missing fields
 */
function generateFollowUpQuestion(missing: string[]): string {
  if (missing.length === 0) return "";

  if (missing.length === 1) {
    return `Before we proceed, I need to know your ${missing[0]}. Could you tell me about that?`;
  }

  if (missing.length === 2) {
    return `I still need a couple of things: your ${missing[0]} and ${missing[1]}. Could you share these details?`;
  }

  // 3+ missing fields
  const lastField = missing.pop();
  return `To create your portfolio, I need to know your ${missing.join(", ")}, and ${lastField}. Let's start with any of these - what would you like to share first?`;
}

/**
 * Process chat message with LLM (Azure OpenAI)
 */
async function processWithLLM(
  message: string,
  currentPolicy: Policy
): Promise<ChatResponse | null> {
  const apiKey = process.env.AZURE_OPENAI_API_KEY;
  const endpoint = process.env.AZURE_OPENAI_ENDPOINT;
  const deployment = process.env.AZURE_OPENAI_DEPLOYMENT || "gpt-4o";

  if (!apiKey || !endpoint) {
    return null; // Fall back to demo mode
  }

  const systemPrompt = `You are a portfolio advisor assistant. Based on the user's message, update their investment policy.

Current policy:
${JSON.stringify(currentPolicy, null, 2)}

Respond with a JSON object containing:
1. "response": A friendly, conversational response to the user
2. "policy": The updated policy object (preserve all existing values, only modify what the user requested)
3. "updates": An array of human-readable strings describing what changed (e.g., "Risk tolerance → conservative")

Rules for policy updates:
- risk_tolerance: "conservative", "moderate", "aggressive", "very_aggressive"
- time_horizon: "short" (<3y), "medium" (3-7y), "long" (7+y)
- exclusions: array of sectors/industries (e.g., ["tobacco", "weapons", "gambling"])
- preferred_themes: array of investment themes (e.g., ["AI", "clean_energy", "healthcare"])
- esg_focus: true/false
- portfolio_value: number in USD
- max_volatility: percentage (e.g., 15 for 15%)
- max_drawdown: percentage
- target_return: percentage
- rebalance_frequency: "monthly", "quarterly", "semi-annual", "annual"

Only output valid JSON, no markdown or explanation.`;

  try {
    const response = await fetch(
      `${endpoint}/openai/deployments/${deployment}/chat/completions?api-version=2024-02-15-preview`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "api-key": apiKey,
        },
        body: JSON.stringify({
          messages: [
            { role: "system", content: systemPrompt },
            { role: "user", content: message },
          ],
          temperature: 0.3,
          max_tokens: 2000,
        }),
      }
    );

    if (!response.ok) {
      console.error("LLM API error:", response.status, await response.text());
      return null;
    }

    const data = await response.json();
    const content = data.choices?.[0]?.message?.content;

    if (!content) {
      return null;
    }

    // Parse the JSON response
    const parsed = JSON.parse(content);
    return {
      response: parsed.response,
      policy: parsed.policy,
      updates: parsed.updates || [],
    };
  } catch (error) {
    console.error("LLM processing error:", error);
    return null;
  }
}

/**
 * Demo mode: Rule-based policy updates
 */
function processWithRules(message: string, currentPolicy: Policy): ChatResponse {
  const lowerMessage = message.toLowerCase();
  const updates: string[] = [];
  const policy = JSON.parse(JSON.stringify(currentPolicy)) as Policy;

  // Initialize nested objects if needed
  policy.risk_appetite = policy.risk_appetite || {};
  policy.preferences = policy.preferences || {};
  policy.constraints = policy.constraints || {};
  policy.benchmark_settings = policy.benchmark_settings || {};
  policy.investor_profile = policy.investor_profile || {};

  // Risk tolerance detection
  if (lowerMessage.includes("conservative") || lowerMessage.includes("low risk") || lowerMessage.includes("safe")) {
    policy.risk_appetite.risk_tolerance = "conservative";
    policy.risk_appetite.max_volatility = 10;
    policy.risk_appetite.max_drawdown = 15;
    updates.push("Risk tolerance → conservative");
    updates.push("Max volatility → 10%");
    updates.push("Max drawdown → 15%");
  } else if (lowerMessage.includes("aggressive") || lowerMessage.includes("high risk") || lowerMessage.includes("growth")) {
    policy.risk_appetite.risk_tolerance = "aggressive";
    policy.risk_appetite.max_volatility = 25;
    policy.risk_appetite.max_drawdown = 35;
    updates.push("Risk tolerance → aggressive");
    updates.push("Max volatility → 25%");
    updates.push("Max drawdown → 35%");
  } else if (lowerMessage.includes("moderate") || lowerMessage.includes("balanced")) {
    policy.risk_appetite.risk_tolerance = "moderate";
    policy.risk_appetite.max_volatility = 15;
    policy.risk_appetite.max_drawdown = 20;
    updates.push("Risk tolerance → moderate");
  }

  // Time horizon detection
  const longTermPatterns = [
    /retirement|retiring/i,
    /long[\s-]?term/i,
    /\b(7|8|9|10|15|20|25|30)\s*(year|yr)/i,
    /\blong\b/i,
  ];
  const shortTermPatterns = [
    /short[\s-]?term/i,
    /\b(1|2)\s*(year|yr)/i,
    /\bshort\b/i,
  ];
  const mediumTermPatterns = [
    /medium[\s-]?term/i,
    /\b(3|4|5|6)\s*(year|yr)/i,
    /\bmedium\b/i,
  ];

  if (longTermPatterns.some(p => p.test(lowerMessage))) {
    policy.risk_appetite.time_horizon = "long";
    updates.push("Time horizon → long-term (7+ years)");
  } else if (shortTermPatterns.some(p => p.test(lowerMessage))) {
    policy.risk_appetite.time_horizon = "short";
    updates.push("Time horizon → short-term (<3 years)");
  } else if (mediumTermPatterns.some(p => p.test(lowerMessage))) {
    policy.risk_appetite.time_horizon = "medium";
    updates.push("Time horizon → medium-term (3-7 years)");
  }

  // ESG/Sustainable investing
  if (lowerMessage.includes("esg") || lowerMessage.includes("sustainable") || lowerMessage.includes("green") || lowerMessage.includes("ethical")) {
    policy.preferences.esg_focus = true;
    updates.push("ESG focus → enabled");
  }

  // Exclusions
  const exclusionKeywords: Record<string, string> = {
    tobacco: "tobacco",
    weapons: "weapons",
    alcohol: "alcohol",
    gambling: "gambling",
    fossil: "fossil_fuels",
    oil: "fossil_fuels",
    coal: "fossil_fuels",
    nuclear: "nuclear",
    defense: "defense",
    firearms: "weapons",
  };

  const currentExclusions = policy.preferences.exclusions || [];
  for (const [keyword, exclusion] of Object.entries(exclusionKeywords)) {
    if (lowerMessage.includes(keyword) && (lowerMessage.includes("exclude") || lowerMessage.includes("no ") || lowerMessage.includes("avoid"))) {
      if (!currentExclusions.includes(exclusion)) {
        currentExclusions.push(exclusion);
        updates.push(`Exclusion added → ${exclusion}`);
      }
    }
  }
  policy.preferences.exclusions = currentExclusions;

  // Themes/Sectors - use word boundary matching to avoid false positives
  const themeKeywords: Record<string, string> = {
    "\\bai\\b": "AI",
    "artificial intelligence": "AI",
    "\\btech\\b": "technology",
    "technology": "technology",
    "healthcare": "healthcare",
    "biotech": "biotechnology",
    "clean energy": "clean_energy",
    "renewable": "clean_energy",
    "solar": "clean_energy",
    "\\bev\\b": "electric_vehicles",
    "electric vehicle": "electric_vehicles",
    "fintech": "fintech",
    "crypto": "cryptocurrency",
    "blockchain": "blockchain",
    "real estate": "real_estate",
    "infrastructure": "infrastructure",
  };

  const currentThemes = policy.preferences.preferred_themes || [];
  const hasThemeIntent = lowerMessage.includes("focus") || lowerMessage.includes("interest") || lowerMessage.includes("like") || lowerMessage.includes("want") || lowerMessage.includes("invest in");
  for (const [pattern, theme] of Object.entries(themeKeywords)) {
    const regex = new RegExp(pattern, "i");
    if (regex.test(lowerMessage) && hasThemeIntent) {
      if (!currentThemes.includes(theme)) {
        currentThemes.push(theme);
        updates.push(`Theme added → ${theme}`);
      }
    }
  }
  policy.preferences.preferred_themes = currentThemes;

  // Portfolio value
  const valueMatch = lowerMessage.match(/\$?([\d,]+(?:\.\d+)?)\s*(million|m|k|thousand)?/i);
  if (valueMatch) {
    let value = parseFloat(valueMatch[1].replace(/,/g, ""));
    const multiplier = valueMatch[2]?.toLowerCase();
    if (multiplier === "million" || multiplier === "m") {
      value *= 1000000;
    } else if (multiplier === "thousand" || multiplier === "k") {
      value *= 1000;
    }
    if (value >= 1000) {
      policy.investor_profile.portfolio_value = value;
      updates.push(`Portfolio value → $${value.toLocaleString()}`);
    }
  }

  // Target return
  const returnMatch = lowerMessage.match(/(\d+(?:\.\d+)?)\s*%?\s*(?:return|yield|target)/i);
  if (returnMatch) {
    const targetReturn = parseFloat(returnMatch[1]);
    if (targetReturn > 0 && targetReturn <= 50) {
      policy.benchmark_settings.target_return = targetReturn;
      updates.push(`Target return → ${targetReturn}%`);
    }
  }

  // Rebalance frequency
  if (lowerMessage.includes("monthly")) {
    policy.benchmark_settings.rebalance_frequency = "monthly";
    updates.push("Rebalance frequency → monthly");
  } else if (lowerMessage.includes("quarterly")) {
    policy.benchmark_settings.rebalance_frequency = "quarterly";
    updates.push("Rebalance frequency → quarterly");
  } else if (lowerMessage.includes("annual") || lowerMessage.includes("yearly")) {
    policy.benchmark_settings.rebalance_frequency = "annual";
    updates.push("Rebalance frequency → annual");
  }

  // Check completeness
  const { ready, missing } = checkPolicyCompleteness(policy);

  // Generate response
  let response: string;
  if (updates.length === 0) {
    // No updates detected - ask for more info
    if (missing.length > 0) {
      response = generateFollowUpQuestion([...missing]);
    } else {
      response = "I understand. Is there anything else you'd like to adjust, or shall I proceed with the current settings?";
    }
  } else {
    // Updates made
    const updateSummary = `I've updated your policy. ${updates.length > 1 ? "Changes:" : "Change:"} ${updates.join(", ")}.`;

    if (ready) {
      response = `${updateSummary} Your policy is now complete and ready to launch! You can click "Launch Portfolio" to start the optimization, or tell me if you'd like to make any more adjustments.`;
    } else if (missing.length > 0) {
      const followUp = generateFollowUpQuestion([...missing]);
      response = `${updateSummary} ${followUp}`;
    } else {
      response = `${updateSummary} Is there anything else you'd like to adjust?`;
    }
  }

  return { response, policy, updates, missingFields: missing, readyToLaunch: ready };
}

/**
 * POST /api/ic/chat
 *
 * Process chat message, check for PII, update policy
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    // Manual validation
    const message = body?.message;
    const current_policy = body?.current_policy;

    if (!message || typeof message !== "string" || message.length < 1 || message.length > 5000) {
      return NextResponse.json(
        { error: "Invalid request body", details: "message must be a string between 1 and 5000 characters" },
        { status: 400 }
      );
    }

    if (!current_policy || typeof current_policy !== "object") {
      return NextResponse.json(
        { error: "Invalid request body", details: "current_policy must be an object" },
        { status: 400 }
      );
    }

    // ═══════════════════════════════════════════════════════════════
    // STEP 1: PII CHECK - Block sensitive information
    // ═══════════════════════════════════════════════════════════════
    console.log("\n" + "=".repeat(70));
    console.log("CHAT MESSAGE PROCESSING");
    console.log("=".repeat(70));
    console.log(`Message: "${message.substring(0, 100)}${message.length > 100 ? "..." : ""}"`);
    console.log("-".repeat(70));
    console.log("Step 1: PII Check");

    const piiResult = await checkPii({ text: message });

    if (piiResult.hasPii) {
      const warningMessage = formatPiiWarning(piiResult.entities);
      const categories = piiResult.entities.map((e) => e.category);

      console.log("PII DETECTED - Message blocked");
      console.log(`Categories: ${categories.join(", ")}`);
      piiResult.entities.forEach((entity) => {
        console.log(`  - "${entity.text}" → ${entity.category} (${(entity.confidenceScore * 100).toFixed(0)}%)`);
      });
      console.log("=".repeat(70) + "\n");

      return NextResponse.json({
        blocked: true,
        error: "pii_detected",
        message: warningMessage,
        detectedCategories: categories,
      });
    }

    console.log("PII Check: PASSED");
    console.log("-".repeat(70));

    // ═══════════════════════════════════════════════════════════════
    // STEP 2: PROCESS MESSAGE - Update policy based on user input
    // ═══════════════════════════════════════════════════════════════
    console.log("Step 2: Processing message");

    // Try LLM first, fall back to rules
    let result = await processWithLLM(message, current_policy as Policy);

    if (result) {
      console.log("Processing: LLM (Azure OpenAI)");
    } else {
      console.log("Processing: Rule-based (demo mode)");
      result = processWithRules(message, current_policy as Policy);
    }

    console.log(`Updates: ${result.updates.length > 0 ? result.updates.join(", ") : "None"}`);
    console.log(`Ready to launch: ${result.readyToLaunch ? "YES" : "NO"}`);
    if (result.missingFields && result.missingFields.length > 0) {
      console.log(`Missing fields: ${result.missingFields.join(", ")}`);
    }
    console.log("=".repeat(70) + "\n");

    // Preserve user's full context for agents to use
    // Append to existing chat_context to build conversation history
    const existingContext = result.policy.chat_context || "";
    const newContext = existingContext
      ? `${existingContext}\n\nUser: ${message}`
      : `User: ${message}`;
    result.policy.chat_context = newContext;

    return NextResponse.json({
      response: result.response,
      policy: result.policy,
      updates: result.updates,
      missingFields: result.missingFields || [],
      readyToLaunch: result.readyToLaunch || false,
    });
  } catch (error) {
    console.error("Chat processing error:", error);
    return NextResponse.json(
      { error: "Failed to process message" },
      { status: 500 }
    );
  }
}
