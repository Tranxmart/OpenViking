// Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
// SPDX-License-Identifier: AGPL-3.0

import { OpenVikingClient } from "../../dist/index.js";
import type {
  CompileSourceContext,
  SourceTimestamp,
} from "../../dist/index.js";

export const client = new OpenVikingClient({
  baseUrl: "https://example.com",
});

// @ts-expect-error the server only accepts local or shared temporary uploads.
new OpenVikingClient({ baseUrl: "https://example.com", uploadMode: "proxy" });

client.getSkill("demo", { targetUri: "viking://agent/skills" });
// @ts-expect-error getSkill accepts one concrete skill root, not multiple roots.
client.getSkill("demo", { targetUri: ["viking://agent/skills"] });

client.exportOVPack("viking://resources/docs", "./docs.ovpack");
client.importOVPack("./docs.ovpack", "viking://resources", {
  onConflict: "overwrite",
  vectorMode: "auto",
});
// @ts-expect-error OVPack conflict policies are restricted by the server.
client.restoreOVPack("./docs.ovpack", { onConflict: "replace" });
client.gitCommit({ message: "snapshot", branch: "main" });

const sourceContext: CompileSourceContext = {
  schema_version: 1,
  sources: [{ uri: "viking://resources/docs/design.md" }],
};
client.compile(
  ["viking://resources/docs"],
  "viking://resources/wiki",
  "viking://agent/skills/wiki",
  { sourceContext },
);
// @ts-expect-error only schema version 1 is supported.
sourceContext.schema_version = 2;
// @ts-expect-error every source requires a native URI.
sourceContext.sources = [{ version: "revision-4" }];
const timestamp: SourceTimestamp = {
  // @ts-expect-error timestamp kinds use the source/work vocabulary.
  kind: "import",
  meaning: "content_modified",
  basis: "origin",
  // @ts-expect-error timestamps must be ISO strings, not numeric epochs.
  value: 1800000000,
};
void timestamp;
