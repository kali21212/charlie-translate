export const screenshotStyles = String.raw`
html,
body {
  margin: 0;
  background: #f6f8fc;
  color: #183153;
  font:
    14px system-ui,
    sans-serif;
}
* {
  box-sizing: border-box;
}
main {
  padding: 14px;
}
label {
  display: block;
  font-weight: 600;
  margin: 12px 0 6px;
}
select,
textarea {
  display: block;
  width: 100%;
  margin-top: 6px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  padding: 8px;
  background: white;
  color: #183153;
  font: inherit;
}
textarea {
  min-height: 100px;
  resize: vertical;
}
.actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
button,
a {
  font: inherit;
}
button {
  border: 0;
  border-radius: 8px;
  padding: 8px 12px;
  background: #2054ad;
  color: white;
  cursor: pointer;
}
button:disabled {
  opacity: 0.45;
  cursor: default;
}
a {
  color: #2054ad;
}
p {
  line-height: 1.5;
  overflow-wrap: anywhere;
}
.note {
  font-size: 12px;
  color: #52647d;
}
.preview {
  display: block;
  max-width: 100%;
  max-height: 180px;
  margin: 8px auto;
  border: 1px solid #cbd5e1;
}
button:focus-visible,
a:focus-visible {
  outline: 3px solid #66baff;
  outline-offset: 2px;
}
`;
