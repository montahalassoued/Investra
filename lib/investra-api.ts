const DEFAULT_INVESTRA_BASE_URL = "http://localhost:8000";

type InvestraResponse = {
  type: "chat" | "investment_advice";
  response: string;
  symbols?: string[];
};

function getInvestraBaseUrl(): string {
  const configuredUrl = process.env.NEXT_PUBLIC_API_URL;

  return (configuredUrl?.trim() || DEFAULT_INVESTRA_BASE_URL).replace(
    /\/$/,
    "",
  );
}

export async function sendMessage(
  message: string,
  sessionId: string,
): Promise<string> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120000);

  try {
    const response = await fetch(`${getInvestraBaseUrl()}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        session_id: sessionId,
      }),
      cache: "no-store",
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`Investra backend request failed (${response.status})`);
    }

    const data = (await response.json()) as Partial<InvestraResponse>;

    if (
      typeof data.response !== "string" ||
      data.response.trim().length === 0
    ) {
      throw new Error("Investra backend returned an invalid response");
    }

    return data.response;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(
        "Investra backend request timed out while generating the analysis",
      );
    }

    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
