import assert from "node:assert/strict";
import { createServer } from "node:http";
import { createClient } from "webdav";
import queryString from "query-string";
import selectorParser from "postcss-selector-parser";

// Exercise the actual upgraded WebDAV XML parser, rather than mocking the client.
const server = createServer((req, res) => {
  assert.equal(req.method, "PROPFIND");
  res.writeHead(207, { "Content-Type": "application/xml" });
  res.end(`<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">
    <d:response><d:href>/charlie/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>
    <d:response><d:href>/charlie/setting.json</d:href><d:propstat><d:prop><d:displayname>setting.json</d:displayname><d:getcontentlength>42</d:getcontentlength><d:resourcetype/></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>
  </d:multistatus>`);
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
try {
  const client = createClient(`http://127.0.0.1:${server.address().port}`);
  const entries = await client.getDirectoryContents("/charlie");
  assert.equal(entries.length, 1);
  assert.equal(entries[0].basename, "setting.json");
  assert.equal(entries[0].size, 42);
  assert.deepEqual(
    { ...queryString.parse("text=Hello%20world&bad=%E0%A4%A") },
    { bad: "%E0%A4%A", text: "Hello world" }
  );
  assert.equal(
    selectorParser().processSync('a[href="/settings"]:not(.secret)'),
    'a[href="/settings"]:not(.secret)'
  );
  console.log(
    "WebDAV XML, URI decoding and selector parser compatibility passed"
  );
} finally {
  await new Promise((resolve, reject) =>
    server.close((error) => (error ? reject(error) : resolve()))
  );
}
