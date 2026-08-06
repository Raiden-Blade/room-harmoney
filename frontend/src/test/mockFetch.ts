import { vi } from "vitest";

export interface MockRoute {
  method?: string;
  test: (url: URL, init?: RequestInit) => boolean;
  handler: (url: URL, init?: RequestInit) => { status?: number; body: unknown };
}

/** テスト用のパスプレフィックス一致ルート定義ヘルパ。 */
export function route(
  method: string,
  pathPrefix: string,
  handler: MockRoute["handler"],
): MockRoute {
  return {
    method,
    test: (url, init) => {
      const reqMethod = (init?.method ?? "GET").toUpperCase();
      return reqMethod === method.toUpperCase() && url.pathname.startsWith(pathPrefix);
    },
    handler,
  };
}

/** `fetch` をルートベースでモックする（各テストの `describe`/`it` 内で呼ぶ）。 */
export function installFetchMock(routes: MockRoute[]) {
  const calls: { url: string; method: string; body: unknown }[] = [];

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const rawUrl = typeof input === "string" ? input : input.toString();
    const url = new URL(rawUrl);
    const method = (init?.method ?? "GET").toUpperCase();
    calls.push({
      url: rawUrl,
      method,
      body: init?.body ? JSON.parse(init.body as string) : undefined,
    });

    const matched = routes.find((r) => r.test(url, init));
    if (!matched) {
      throw new Error(`No mock route registered for ${method} ${rawUrl}`);
    }
    const { status = 200, body } = matched.handler(url, init);
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });

  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}
