import test from "node:test";
import assert from "node:assert/strict";
import {
  buildPlannerMessages,
  listOpenZeroModels,
  parsePlannerResponse,
  requestBrowserAction
} from "../src/shared/openzero-client.js";

const snapshot = {
  snapshot_id: "snap-1",
  url: "https://example.com/",
  title: "Example",
  text: "Untrusted page text",
  headings: [],
  interactive: [{ id: "e1", label: "Learn more" }],
  viewport: { width: 1000, height: 700 }
};

test("planner parser accepts exactly one JSON action", () => {
  assert.deepEqual(
    parsePlannerResponse('{"action":"click","element_id":"e1","reason":"open details"}'),
    { action: "click", element_id: "e1", reason: "open details" }
  );
});

test("planner parser tolerates a single JSON code fence but rejects prose", () => {
  assert.equal(
    parsePlannerResponse('```json\n{"action":"finish","message":"Done"}\n```').action,
    "finish"
  );
  assert.throws(
    () => parsePlannerResponse('I will do it. {"action":"finish","message":"Done"}'),
    /non-JSON/i
  );
});

test("planner messages mark snapshots untrusted and never include a key", () => {
  const messages = buildPlannerMessages({
    task: "Read the page",
    snapshot,
    step: 1,
    history: []
  });
  assert.match(messages[0].content, /untrusted/i);
  assert.match(messages[1].content, /page_snapshot_untrusted/);
  assert.doesNotMatch(JSON.stringify(messages), /Bearer|apiKey|test-key/);
});

test("OpenZero request uses authenticated compatible route and parses action", async () => {
  let captured;
  const action = await requestBrowserAction({
    settings: {
      apiBaseUrl: "http://127.0.0.1:1024",
      apiKey: "unit-test-key",
      model: "openzerogemma:latest",
      openzeroSpark: "auto"
    },
    task: "Open details",
    snapshot,
    step: 1,
    history: [],
    fetchImpl: async (url, init) => {
      captured = { url, init };
      return new Response(
        JSON.stringify({ action: { action: "click", element_id: "e1" } }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
  });
  assert.equal(captured.url, "http://127.0.0.1:1024/v1/browser/plan");
  assert.equal(captured.init.headers.Authorization, "Bearer unit-test-key");
  assert.equal(JSON.parse(captured.init.body).model, "openzerogemma:latest");
  assert.equal(JSON.parse(captured.init.body).snapshot.text, "Untrusted page text");
  assert.equal(action.action, "click");
});

test("model discovery returns IDs and reports authentication errors", async () => {
  const models = await listOpenZeroModels({
    apiBaseUrl: "http://localhost:1024",
    apiKey: "unit-test-key",
    fetchImpl: async () =>
      new Response(JSON.stringify({ data: [{ id: "openzerogemma:latest" }, { id: "" }] }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      })
  });
  assert.deepEqual(models, ["openzerogemma:latest"]);

  await assert.rejects(
    () =>
      listOpenZeroModels({
        apiBaseUrl: "http://localhost:1024",
        apiKey: "wrong-key",
        fetchImpl: async () =>
          new Response(JSON.stringify({ error: { message: "Unauthorized" } }), {
            status: 401,
            headers: { "Content-Type": "application/json" }
          })
      }),
    /Unauthorized/
  );
});
