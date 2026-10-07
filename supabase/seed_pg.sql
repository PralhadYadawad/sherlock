
INSERT INTO targets (id, case_id, kind, label, created_at) VALUES
  ('tgt-demo-sleuth', 'DEMO-CASE-001', 'username', '@demo.sleuth', CURRENT_TIMESTAMP),
  ('tgt-demo-domain', 'DEMO-CASE-001', 'domain', 'example.com', CURRENT_TIMESTAMP),
  ('tgt-demo-reel', 'DEMO-CASE-001', 'reel', 'https://www.instagram.com/reel/DMYosint001/', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING;

INSERT INTO findings (id, case_id, type, value, source, confidence, created_at) VALUES
  ('f-username-1', 'DEMO-CASE-001', 'presence', 'DemoHub: https://example.com/users/demo.sleuth', 'username_probe', 'medium', CURRENT_TIMESTAMP),
  ('f-username-2', 'DEMO-CASE-001', 'presence', 'DemoCode: https://example.com/@demo.sleuth', 'username_probe', 'medium', CURRENT_TIMESTAMP),
  ('f-username-3', 'DEMO-CASE-001', 'presence', 'DemoBlog: https://example.com/blog/demo.sleuth', 'username_probe', 'medium', CURRENT_TIMESTAMP),
  ('f-domain-1', 'DEMO-CASE-001', 'subdomain', 'blog.example.com', 'domain_intel', 'medium', CURRENT_TIMESTAMP),
  ('f-domain-2', 'DEMO-CASE-001', 'subdomain', 'www.example.com', 'domain_intel', 'medium', CURRENT_TIMESTAMP),
  ('f-domain-3', 'DEMO-CASE-001', 'contact', 'admin@example.com', 'domain_intel', 'low', CURRENT_TIMESTAMP),
  ('f-reel-1', 'DEMO-CASE-001', 'author', '@demo.archivist', 'oembed_public', 'medium', CURRENT_TIMESTAMP),
  ('f-reel-2', 'DEMO-CASE-001', 'caption', 'open-source research notes: tracing public handles across demo sites for DEMO-CASE-001. Methods only, no private data.', 'oembed_public', 'medium', CURRENT_TIMESTAMP),
  ('f-reel-3', 'DEMO-CASE-001', 'transcript_link', 'https://example.com/resource-1', 'oembed_public', 'low', CURRENT_TIMESTAMP),
  ('f-reel-4', 'DEMO-CASE-001', 'transcript_link', 'https://example.com/resource-2', 'oembed_public', 'low', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING;

INSERT INTO fetch_log (adapter, target, status, reason, created_at) VALUES
  ('username_probe', '@demo.sleuth', 'ok', 'seed', CURRENT_TIMESTAMP),
  ('domain_intel', 'example.com', 'ok', 'seed', CURRENT_TIMESTAMP),
  ('oembed_public', 'https://www.instagram.com/reel/DMYosint001/', 'ok', 'seed', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING;
