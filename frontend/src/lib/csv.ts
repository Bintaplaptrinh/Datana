export function parseCsv(input: string): string[][] {
  const rows: string[][] = [[]];
  let field = "";
  let quoted = false;

  for (let index = 0; index < input.length; index += 1) {
    const character = input[index];
    if (quoted) {
      if (character === '"' && input[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (character === '"') {
        quoted = false;
      } else {
        field += character;
      }
    } else if (character === '"') {
      quoted = true;
    } else if (character === ",") {
      rows[rows.length - 1].push(field);
      field = "";
    } else if (character === "\n") {
      rows[rows.length - 1].push(field);
      rows.push([]);
      field = "";
    } else if (character !== "\r") {
      field += character;
    }
  }

  rows[rows.length - 1].push(field);
  if (rows.length > 1 && rows[rows.length - 1].length === 1 && rows[rows.length - 1][0] === "") {
    rows.pop();
  }
  return rows;
}

function encodeCell(value: string): string {
  return /[",\r\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
}

export function serializeCsv(rows: string[][]): string {
  return `${rows.map((row) => row.map(encodeCell).join(",")).join("\n")}\n`;
}
