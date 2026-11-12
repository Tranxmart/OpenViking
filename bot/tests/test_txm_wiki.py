"""TXM Skill packaging, output contracts and opt-in real-model compilation fixtures.

The artifact checker is an acceptance-test oracle, not publication-time enforcement.
Set TXM_WIKI_EVAL_CONFIG to a private OpenAI-compatible VLM JSON config to run models.
"""

import hashlib
import json
import os
import posixpath
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit

import pytest
import yaml
from vikingbot.agent.tools.base import Tool
from vikingbot.compile import entry
from vikingbot.compile.hashing import content_hash
from vikingbot.compile.models import CompileLimits, SanitizedCompileRequest
from vikingbot.compile.pipeline import Pipeline
from vikingbot.compile.skill_resources import SkillResources
from vikingbot.compile.sources import split_source

from openviking_cli.exceptions import NotFoundError, OpenVikingError
from scripts.build_support.system_assets_manifest import build_system_assets_manifest

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "openviking/system_assets"
SKILL = ASSETS / "compile/example-skills/txm-wiki"
CASES = Path(__file__).parent / "fixtures/txm_wiki/cases.yaml"
SKILL_URI = "viking://system/compile/example-skills/txm-wiki"
TARGET = "viking://resources/txm-wiki-fixture"
SOURCE = "viking://resources/txm-wiki-evidence"
LINK = re.compile(r"\[[^\]]+\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)")


def policy():
    return yaml.safe_load((SKILL / "references/topics.yaml").read_text())


def markdown(kind, title, body):
    metadata = yaml.safe_dump(
        {"type": kind, "title": title, "description": f"Knowledge about {title}."},
        sort_keys=False,
    )
    return f"---\n{metadata}---\n# {title}\n\n{body}\n"


def parse_page(content):
    assert content.startswith("---\n"), "Missing OKF frontmatter"
    head, body = content[4:].split("\n---\n", 1)
    metadata = yaml.safe_load(head)
    for field in ("type", "title", "description"):
        assert isinstance(metadata.get(field), str) and metadata[field].strip(), field
    assert "\n" not in metadata["description"], "Description must occupy one line"
    assert re.findall(r"^# (.+)$", body, re.MULTILINE) == [metadata["title"]]
    return metadata, body


def article_links(path, body, files, sources):
    result = []
    for target in LINK.findall(body):
        parsed = urlsplit(target)
        if parsed.scheme == "viking":
            if target.split("#", 1)[0] in sources:
                continue
            assert target.startswith(TARGET + "/"), f"Unknown native destination: {target}"
            resolved = unquote(parsed.path).removeprefix(urlsplit(TARGET).path + "/")
        elif parsed.scheme:
            assert target in sources, f"Invented external source: {target}"
            continue
        elif not parsed.path:
            continue
        else:
            resolved = posixpath.normpath(
                posixpath.join(posixpath.dirname(path), unquote(parsed.path))
            )
        assert resolved in files, f"Broken link in {path}: {target}"
        if resolved != "index.md" and not resolved.endswith("/index.md"):
            result.append(resolved)
    return result


def check_wiki(files, sources):
    """Check the complete fixture target, including historical unchanged articles."""
    config = policy()
    enabled = {key for key, value in config["topics"].items() if value["enabled"]}
    indexes = {"index.md"} | {f"topics/{key}/index.md" for key in enabled}
    assert indexes <= files.keys(), "Missing root or enabled-topic catalog"
    pages, bodies, articles = {}, {}, set()
    for path, content in files.items():
        parts = PurePosixPath(path).parts
        assert ".." not in parts and not path.startswith("/")
        metadata, body = parse_page(content)
        pages[path], bodies[path] = metadata, body
        if path in indexes:
            assert metadata["type"] == "index"
        else:
            assert len(parts) == 4 and parts[0] == "topics", f"Invalid article path: {path}"
            assert parts[1] in enabled and parts[2] in config["categories"], path
            assert parts[3].endswith(".md") and not parts[3].startswith("."), path
            assert parts[3] != "index.md", "Category indexes are not part of this contract"
            assert metadata["type"] == parts[2], f"Path/type mismatch: {path}"
            articles.add(path)
    links = {p: article_links(p, body, files, sources) for p, body in bodies.items()}
    assert not links["index.md"], "Root must route topics, not dump articles"
    root_links = LINK.findall(bodies["index.md"])
    for key in enabled:
        expected = f"topics/{key}/index.md"
        assert any(
            link in {expected, "./" + expected, TARGET + "/" + expected} for link in root_links
        )
        topic_index = f"topics/{key}/index.md"
        expected_articles = {p for p in articles if p.startswith(f"topics/{key}/")}
        assert set(links[topic_index]) == expected_articles, f"Incomplete catalog: {key}"
        assert len(links[topic_index]) == len(expected_articles), f"Duplicate entries: {key}"
        for article in expected_articles:
            assert pages[article]["title"] in bodies[topic_index], article
            entries = [
                line
                for line in bodies[topic_index].splitlines()
                if article in article_links(topic_index, line, files, sources)
            ]
            assert any(LINK.sub("", line).strip(" |-*—:;") for line in entries), (
                f"Missing retrieval description: {article}"
            )
    assert "users" in bodies["index.md"].lower(), "Reserved topic must be marked disabled"
    assert not any("users" in link for link in root_links), "Disabled topic has a destination"
    assert not any(path.startswith("topics/users/") for path in files)
    return pages, bodies, articles


def example_wiki():
    files = {}
    rows = []
    for key, value in policy()["topics"].items():
        if value["enabled"]:
            rows.append(f"- [{key}](topics/{key}/index.md): {value['scope']} {value['boundary']}")
            files[f"topics/{key}/index.md"] = markdown("index", key, "No articles yet.")
        else:
            rows.append(f"- {key}: reserved and disabled; no destination.")
    files["index.md"] = markdown("index", "TXM Wiki", "\n".join(rows))
    path = "topics/infra/entity/artifact-relay.md"
    files[path] = markdown("entity", "Artifact Relay", "An immutable artifact cache.")
    files["topics/infra/index.md"] = markdown(
        "index",
        "infra",
        "- [Artifact Relay](entity/artifact-relay.md): Knowledge about Artifact Relay.",
    )
    return files


def test_topic_policy_and_packaged_manifest():
    config = policy()
    assert config["version"] == 2 and config["fallback_topic"] == "general"
    assert set(config["categories"]) == {
        "entity",
        "concept",
        "method",
        "comparison",
        "analysis",
    }
    assert set(config["topics"]) == {
        "general",
        "infra",
        "hardware",
        "perception",
        "planning",
        "sensors",
        "canbus",
        "localization",
        "control",
        "testqa",
        "system",
        "map",
        "users",
    }
    assert {key for key, value in config["topics"].items() if not value["enabled"]} == {"users"}
    assert all(
        value["scope"].strip() and value["boundary"].strip() for value in config["topics"].values()
    )
    assert (ASSETS / "manifest.json").read_bytes() == build_system_assets_manifest(ASSETS)
    assert (ASSETS / "compile/example-skills/llm-wiki/SKILL.md").is_file()


@pytest.mark.parametrize(
    "damage", ["missing", "duplicate", "broken", "type", "reference", "users", "sidecar", "flat"]
)
def test_artifact_checker_rejects_contract_violations(damage):
    files = example_wiki()
    if damage == "missing":
        files["topics/infra/index.md"] = markdown("index", "infra", "No articles yet.")
    elif damage == "duplicate":
        files["topics/infra/index.md"] += "\n- [Again](entity/artifact-relay.md)\n"
    elif damage == "broken":
        files["topics/infra/index.md"] += "\n- [Ghost](entity/ghost.md)\n"
    elif damage == "type":
        files["topics/infra/entity/artifact-relay.md"] = markdown(
            "summary", "Artifact Relay", "Cache."
        )
    elif damage == "reference":
        files["topics/canbus/reference/wire-spec.md"] = markdown(
            "reference", "WireSpec", "A CAN signal specification."
        )
        files["topics/canbus/index.md"] = markdown(
            "index", "canbus", "- [WireSpec](reference/wire-spec.md): A CAN signal specification."
        )
    elif damage == "users":
        files["topics/users/entity/profile.md"] = markdown("entity", "Profile", "Disabled.")
    elif damage == "sidecar":
        files[".overview.md"] = markdown("index", "Overview", "Duplicate navigation.")
    else:
        files["entity/flat.md"] = markdown("entity", "Flat", "Wrong layout.")
    with pytest.raises(AssertionError):
        check_wiki(files, set())


def test_artifact_checker_preserves_historical_and_empty_topics():
    files = example_wiki()
    check_wiki(files, set())
    files["topics/infra/entity/artifact-relay.md"] += "\nA new, complementary fact.\n"
    check_wiki(files, set())


class FixtureSandbox:
    """Task-owned files only; no model-accessible command execution or host tools."""

    def __init__(self, root):
        self.sandbox_cwd = str(root.resolve())

    def local_file_path(self, path):
        resolved = (Path(self.sandbox_cwd) / path).resolve()
        if not resolved.is_relative_to(self.sandbox_cwd):
            raise ValueError("Outside fixture sandbox")
        return resolved

    async def write_file(self, path, content):
        destination = self.local_file_path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")

    async def read_file_bytes(self, path):
        return self.local_file_path(path).read_bytes()


class FixtureClient:
    """In-memory OpenViking storage boundary; original Skill/resources are real files."""

    def __init__(self):
        self.documents = {
            SKILL_URI + "/" + p.relative_to(SKILL).as_posix(): p.read_text()
            for p in SKILL.rglob("*")
            if p.is_file()
        }

    async def stat(self, uri):
        if uri not in self.documents:
            raise NotFoundError(uri)
        return {"size": len(self.documents[uri].encode()), "isDir": False}

    async def download_bytes(self, uri):
        await self.stat(uri)
        return self.documents[uri].encode()

    async def read_raw(self, uri, limit=None):
        text = (await self.download_bytes(uri)).decode()
        return text if limit is None else "\n".join(text.splitlines()[:limit])

    async def list_resources(self, uri, node_limit=100):
        return [
            {"uri": p, "isDir": False} for p in sorted(self.documents) if p.startswith(uri + "/")
        ][:node_limit]

    async def find(self, query, target_uri, limit=4):
        words = set(re.findall(r"\w+", query.lower()))
        matches = [
            (len(words & set(re.findall(r"\w+", text.lower()))), uri)
            for uri, text in self.documents.items()
            if uri.startswith(target_uri + "/")
        ]
        return {"resources": [{"uri": uri} for _, uri in sorted(matches, reverse=True)[:limit]]}

    async def compile_embeddings(self, texts, **kwargs):
        # Exercise supported text candidate fallback without a second model endpoint.
        raise OpenVikingError("Fixture storage has no embedding endpoint", code="UNAVAILABLE")

    def outputs(self):
        return {
            uri.removeprefix(TARGET + "/"): text
            for uri, text in self.documents.items()
            if uri.startswith(TARGET + "/")
        }


class TargetReader(Tool):
    name = "openviking_multi_read"
    description = "Read known fixture target URIs with their content revision."
    parameters = {
        "type": "object",
        "properties": {"uris": {"type": "array", "items": {"type": "string"}}},
        "required": ["uris"],
    }

    def __init__(self, client):
        self.client = client

    async def execute(self, tool_context=None, uris=(), **kwargs):
        results = []
        for uri in uris:
            if not uri.startswith(TARGET + "/"):
                raise ValueError("Outside fixture target")
            try:
                content = await self.client.read_raw(uri)
            except NotFoundError:
                results.append({"uri": uri, "success": False, "error": "NOT_FOUND"})
            else:
                results.append(
                    {
                        "uri": uri,
                        "success": True,
                        "content": content,
                        "base_hash": content_hash(content),
                    }
                )
        return json.dumps({"results": results})


@pytest.mark.asyncio
async def test_skill_resource_is_loaded_and_versioned(tmp_path):
    client = FixtureClient()
    from vikingbot.compile.pipeline_io import TaskFiles

    resources = SkillResources(client, SKILL_URI, TaskFiles(FixtureSandbox(tmp_path)))
    response = json.loads(await resources.execute(path="references/topics.yaml"))
    assert response["complete"] and yaml.safe_load(response["text"]) == policy()
    assert Path(response["local_path"]).read_text() == response["text"]
    original = dict(resources.hashes)
    client.documents[SKILL_URI + "/references/topics.yaml"] += "\n# Changed policy\n"
    assert not await resources.valid(original)
    with pytest.raises(ValueError):
        await resources.execute(path="../another-skill/topics.yaml")


def check_subjects(files, sources, cases):
    pages, bodies, articles = check_wiki(files, sources)
    for subject in cases["subjects"]:
        candidates = [
            p
            for p in articles
            if p.startswith(f"topics/{subject['topic']}/")
            and subject["name"].casefold() in pages[p]["title"].casefold()
        ]
        assert candidates, f"Missing canonical subject: {subject['name']}"
        text = "\n".join(bodies[p] for p in candidates)
        for detail in subject["contains"]:
            assert str(detail).casefold() in text.casefold(), f"Lost {detail}: {subject['name']}"
        if "category" in subject:
            assert len([p for p in candidates if pages[p]["type"] == subject["category"]]) == 1
        for alias in subject.get("aliases", []):
            assert re.search(rf"\b{re.escape(alias)}\b", text)
            assert alias in bodies[f"topics/{subject['topic']}/index.md"]
    all_text = "\n".join(files.values())
    assert all(token not in all_text for token in cases["forbidden"]), (
        "Source instruction/metadata leaked"
    )
    for source_name in cases["sources"]:
        assert not any(PurePosixPath(p).stem == Path(source_name).stem for p in articles)
    relay = next(
        p
        for p in articles
        if pages[p]["type"] == "entity" and "Artifact Relay" in pages[p]["title"]
    )
    assert sum(uri in bodies[relay] for uri in sources) >= 2, "No cross-source synthesis evidence"
    assert any(
        PurePosixPath(link).parts[1] != PurePosixPath(path).parts[1]
        for path in articles
        for link in article_links(path, bodies[path], files, sources)
    ), "Missing cross-topic relationship"
    return relay


@pytest.mark.skipif(
    not os.environ.get("TXM_WIKI_EVAL_CONFIG"),
    reason="Set TXM_WIKI_EVAL_CONFIG for real-model acceptance",
)
@pytest.mark.parametrize("mode", ["direct", "collection"])
@pytest.mark.asyncio
async def test_model_compilation(tmp_path, monkeypatch, mode):
    from vikingbot.providers.vlm_adapter import VLMProviderAdapter

    from openviking.models.vlm.backends.openai_vlm import OpenAIVLM

    config = json.loads(Path(os.environ["TXM_WIKI_EVAL_CONFIG"]).read_text())
    cases = yaml.safe_load(CASES.read_text())
    skill_text = (SKILL / "SKILL.md").read_text()
    input_hashes = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (SKILL / "SKILL.md", SKILL / "references/topics.yaml", CASES, Path(__file__))
    }
    provider = VLMProviderAdapter(OpenAIVLM(config), config["model"])
    client = FixtureClient()
    output_root = Path(os.environ.get("TXM_WIKI_EVAL_OUTPUT", str(tmp_path)))
    output_root.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix=mode + "-", dir=output_root))
    runs = []
    outcome = "failed"

    async def compile_fixture(sources, label):
        sandbox = FixtureSandbox(destination / label)
        runtime = Pipeline(
            client=client,
            sandbox=sandbox,
            provider=provider,
            model=config["model"],
            temperature=0,
            limits=CompileLimits(source_concurrency=2, merge_concurrency=2),
            request=SanitizedCompileRequest(
                **{
                    "from": [SOURCE],
                    "to": TARGET,
                    "skill": SKILL_URI,
                    "instruction": "Compile the supplied synthetic engineering evidence into a TXM wiki in English. "
                    "Use direct execution for transforms: these bounded fixtures provide scoped reading tools, "
                    "not an agent or command executor. Preserve all Skill requirements.",
                }
            ),
            skill=skill_text,
            usage={},
        )
        runtime.tools = {"openviking_multi_read": TargetReader(client)}
        runtime.tool_context = SimpleNamespace()
        await runtime.files.put("inputs", {SOURCE + "/" + name: "pending" for name in sources})

        async def batches():
            for name, content in sources.items():
                yield split_source(SOURCE + "/" + name, content, 600)

        bundle = await runtime.run(batches())
        assert not runtime.failures, runtime.failures
        for operation in bundle.operations:
            assert operation["uri"].startswith(TARGET + "/")
            exists = operation["uri"] in client.documents
            assert exists == (operation["mode"] == "replace"), (
                f"Invalid {operation['mode']} for fixture target: {operation['uri']}"
            )
            client.documents[operation["uri"]] = operation["content"]
        assert "references/topics.yaml" in runtime.resources.hashes, "Policy was never loaded"
        await runtime.write_coverage([op["uri"] for op in bundle.operations])
        output = client.outputs()
        for path, text in output.items():
            target = destination / label / "wiki" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        runs.append(
            {
                "label": label,
                "metrics": dict(runtime.metrics),
                "usage": runtime.model.usage,
                "files": {p: content_hash(text) for p, text in output.items()},
            }
        )
        return output, runtime

    try:
        if mode == "collection":

            async def request_pipeline(*args, **kwargs):
                return None

            monkeypatch.setattr(entry, "run", request_pipeline)
        files, runtime = await compile_fixture(cases["sources"], "initial")
        assert bool(runtime.metrics["direct_completed"]) == (mode == "direct")
        if mode == "collection":
            assert all(runtime.metrics[f"{stage}_calls"] for stage in ("plan", "map", "reduce"))
        source_uris = {SOURCE + "/" + name for name in cases["sources"]}
        relay = check_subjects(files, source_uris, cases)
        client.documents[TARGET + "/" + relay] += (
            "\nManual context: HAND-KEPT-2214 remains applicable.\n"
        )
        previous = client.outputs()
        files, _ = await compile_fixture(cases["incremental"], "incremental")
        assert relay in files and "cache_probe_total" in files[relay]
        assert "HAND-KEPT-2214" in files[relay]
        source_uris |= {SOURCE + "/" + name for name in cases["incremental"]}
        check_subjects(files, source_uris, cases)
        for path, text in previous.items():
            if path != relay and not path.endswith("index.md"):
                assert files[path] == text, f"Unrelated historical page changed: {path}"
        before_repeat = set(files)
        files, _ = await compile_fixture(cases["incremental"], "repeat")
        assert set(files) == before_repeat, "Repeat compilation created duplicate subjects"
        check_subjects(files, source_uris, cases)
        outcome = "passed"
    finally:
        evidence = {
            "outcome": outcome,
            "fork_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "inputs": input_hashes,
            "model": {
                key: config.get(key)
                for key in ("provider", "model", "api_base", "max_tokens", "timeout")
            },
            "runs": runs,
        }
        (destination / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
