//! Mappack definition files in JSON — the format ZedSuite itself exports for
//! WinOLS, and the one most sharing tools use.
//!
//! A mappack is a plain list of map descriptions: name, folder, grid, the
//! address of the values, the two axis addresses, and the factor/offset that
//! turn raw cells into physical units. It carries no ROM: the user opens
//! their binary, then imports the mappack that goes with it.
//!
//! Shape accepted, in order: `{"maps": [...]}` (what ZedSuite writes), a bare
//! array of map objects, or `{"Maps": [...]}`. Inside a map object the keys
//! are the flat dotted ones WinOLS uses (`Fieldvalues.StartAddr.Cpu`,
//! `AxisX.Factor`…); nested objects (`{"Fieldvalues": {"Factor": …}}`) are
//! read too, and numbers may be written as numbers or as strings.
//!
//! Anything that does not describe a usable map is skipped rather than
//! guessed: no name, no address, a grid of zero, a cell size that is not 1,
//! 2 or 4 bytes, or a block that would fall outside the binary.

use serde_json::Value;

use crate::models::{DataType, DetectedMap, MapDimensions};

/// A grid larger than this is a misread field, not a map.
const MAX_DIM: u32 = 4096;

/// Reads every map of a JSON mappack. `rom_len` is the size of the binary the
/// definitions apply to: a map that would not fit is left out. Pass 0 to skip
/// that check.
pub fn parse_mappack(text: &str, rom_len: u32) -> Result<Vec<DetectedMap>, String> {
    let root: Value = serde_json::from_str(text).map_err(|e| format!("invalid JSON: {e}"))?;
    let list = map_list(&root).ok_or("no map list in this JSON file")?;
    Ok(list.iter().filter_map(|m| to_map(m, rom_len)).collect())
}

fn map_list(root: &Value) -> Option<&Vec<Value>> {
    match root {
        Value::Array(a) => Some(a),
        Value::Object(o) => ["maps", "Maps", "MAPS", "kennfelder", "tables"]
            .iter()
            .find_map(|k| o.get(*k))
            .and_then(|v| v.as_array()),
        _ => None,
    }
}

/// Value of `key` in a map object: the flat dotted key first (`AxisX.Factor`),
/// then the same path walked through nested objects.
fn field<'a>(obj: &'a Value, key: &str) -> Option<&'a Value> {
    let o = obj.as_object()?;
    if let Some(v) = o.get(key) {
        return Some(v);
    }
    let mut cur = obj;
    for part in key.split('.') {
        cur = cur.as_object()?.get(part)?;
    }
    Some(cur)
}

fn text_of(obj: &Value, key: &str) -> Option<String> {
    match field(obj, key)? {
        Value::String(s) => Some(s.clone()),
        Value::Number(n) => Some(n.to_string()),
        Value::Bool(b) => Some(if *b { "1".into() } else { "0".into() }),
        _ => None,
    }
}

fn number_of(obj: &Value, key: &str) -> Option<f64> {
    match field(obj, key)? {
        Value::Number(n) => n.as_f64(),
        Value::String(s) => s.trim().replace(',', ".").parse::<f64>().ok(),
        _ => None,
    }
}

fn flag_of(obj: &Value, key: &str) -> bool {
    match field(obj, key) {
        Some(Value::Bool(b)) => *b,
        Some(Value::Number(n)) => n.as_f64().unwrap_or(0.0) != 0.0,
        Some(Value::String(s)) => {
            let s = s.trim();
            s == "1" || s.eq_ignore_ascii_case("true")
        }
        _ => false,
    }
}

/// "$1A2B" (WinOLS), "0x1A2B", a decimal string, or a JSON number.
fn address_of(obj: &Value, key: &str) -> Option<u32> {
    match field(obj, key)? {
        Value::Number(n) => {
            let v = n.as_f64()?;
            (v >= 0.0 && v <= u32::MAX as f64).then_some(v as u32)
        }
        Value::String(s) => {
            let s = s.trim();
            if let Some(hex) = s.strip_prefix('$') {
                return u32::from_str_radix(hex.trim_start_matches("0x"), 16).ok();
            }
            if let Some(hex) = s.strip_prefix("0x").or_else(|| s.strip_prefix("0X")) {
                return u32::from_str_radix(hex, 16).ok();
            }
            s.parse::<u32>().ok().or_else(|| u32::from_str_radix(s, 16).ok())
        }
        _ => None,
    }
}

/// Cell size in bytes, byte order and float flag, from the WinOLS `DataOrg`
/// word. `eByte` = 8 bits, `eLoHi`/`eHiLo` = 16, the doubled forms = 32,
/// `eFloat` = a 32-bit float. `None` for a word this module does not know.
fn data_org(word: &str) -> Option<(u32, bool, bool)> {
    let lowered = word.trim().to_lowercase();
    let w = lowered.strip_prefix('e').unwrap_or(&lowered);
    Some(match w {
        "byte" | "int8" | "uint8" | "8" => (1, false, false),
        "lohi" | "16lohi" | "word" => (2, true, false),
        "hilo" | "16hilo" => (2, false, false),
        "lohilohi" | "32lohi" | "longlohi" => (4, true, false),
        "hilohilo" | "32hilo" | "long" | "longhilo" => (4, false, false),
        "float" | "floatlohi" => (4, true, true),
        "floathilo" => (4, false, true),
        _ => return None,
    })
}

fn to_map(obj: &Value, rom_len: u32) -> Option<DetectedMap> {
    let name = text_of(obj, "Name")
        .or_else(|| text_of(obj, "name"))
        .or_else(|| text_of(obj, "IdName"))
        .or_else(|| text_of(obj, "title"))?;
    let name = name.trim().to_string();
    if name.is_empty() {
        return None;
    }

    let address = address_of(obj, "Fieldvalues.StartAddr.Cpu")
        .or_else(|| address_of(obj, "Fieldvalues.StartAddr"))
        .or_else(|| address_of(obj, "StartAddr.Cpu"))
        .or_else(|| address_of(obj, "address"))
        .or_else(|| address_of(obj, "Address"))?;

    let cols = number_of(obj, "Columns").or_else(|| number_of(obj, "cols")).unwrap_or(1.0).round();
    let rows = number_of(obj, "Rows").or_else(|| number_of(obj, "rows")).unwrap_or(1.0).round();
    if !(1.0..=MAX_DIM as f64).contains(&cols) || !(1.0..=MAX_DIM as f64).contains(&rows) {
        return None;
    }
    let (cols, rows) = (cols as u32, rows as u32);

    let org = text_of(obj, "DataOrg")
        .or_else(|| text_of(obj, "data_org"))
        .unwrap_or_else(|| "eLoHi".to_string());
    let (cell, little_endian, is_float) = data_org(&org)?;
    let signed = flag_of(obj, "bSigned") || flag_of(obj, "signed");

    let size = rows as u64 * cols as u64 * cell as u64;
    if size == 0 || size > u32::MAX as u64 {
        return None;
    }
    if rom_len > 0 && address as u64 + size > rom_len as u64 {
        return None;
    }

    let data_type = if is_float {
        DataType::Float32
    } else {
        match (cell, signed) {
            (1, true) => DataType::Int8,
            (1, false) => DataType::UInt8,
            (2, true) => DataType::Int16,
            (2, false) => DataType::UInt16,
            (_, true) => DataType::Int32,
            (_, false) => DataType::UInt32,
        }
    };

    // Une seule ligne de N colonnes = une courbe, comme la produit le
    // détecteur : même rendu, et un export réimporté retrouve sa forme.
    let dimensions = if rows == 1 && cols > 1 {
        MapDimensions::OneDimensional { length: cols as usize }
    } else {
        MapDimensions::TwoDimensional { rows: rows as usize, cols: cols as usize }
    };

    let mut d = DetectedMap::new(address, size as usize, dimensions, data_type);
    d.external_source = Some("JSON".to_string());
    d.name = Some(name.clone());
    let comment = text_of(obj, "Comment").or_else(|| text_of(obj, "description")).unwrap_or_default();
    d.description = Some(if comment.trim().is_empty() {
        format!("Imported definition {name}")
    } else {
        comment.trim().to_string()
    });
    // « Z-Other » est le dossier que l'app écrit pour garder « Other » en bas
    // de la liste dans WinOLS : il revient sous son vrai nom.
    let raw_folder = text_of(obj, "FolderName")
        .or_else(|| text_of(obj, "folder"))
        .or_else(|| text_of(obj, "category"))
        .map(|f| f.trim().to_string())
        .filter(|f| !f.is_empty())
        .unwrap_or_else(|| "Other".to_string());
    let folder = raw_folder.strip_prefix("Z-").unwrap_or(&raw_folder).to_string();
    d.category = Some(folder.clone());
    d.subcategory = Some(folder);
    d.unit = text_of(obj, "Fieldvalues.Unit").or_else(|| text_of(obj, "unit"));
    d.correction_factor = Some(
        number_of(obj, "Fieldvalues.Factor")
            .or_else(|| number_of(obj, "factor"))
            .filter(|f| f.is_finite() && *f != 0.0)
            .unwrap_or(1.0),
    );
    d.offset = Some(
        number_of(obj, "Fieldvalues.Offset")
            .or_else(|| number_of(obj, "offset"))
            .filter(|f| f.is_finite())
            .unwrap_or(0.0),
    );
    d.confidence = 1.0;
    if little_endian && cell > 1 {
        d.is_little_endian = Some(true);
    }

    for (prefix, alt, is_x) in [("AxisX", "x_axis", true), ("AxisY", "y_axis", false)] {
        let addr = address_of(obj, &format!("{prefix}.DataAddr.Cpu"))
            .or_else(|| address_of(obj, &format!("{prefix}.DataAddr")))
            .or_else(|| address_of(obj, &format!("{alt}_address")))
            .filter(|a| *a > 0);
        let factor = number_of(obj, &format!("{prefix}.Factor"))
            .or_else(|| number_of(obj, &format!("{alt}_correction")))
            .filter(|f| f.is_finite() && *f != 0.0)
            .unwrap_or(1.0);
        let off = number_of(obj, &format!("{prefix}.Offset"))
            .or_else(|| number_of(obj, &format!("{alt}_offset")))
            .filter(|f| f.is_finite() && *f != 0.0);
        let label = text_of(obj, &format!("{prefix}.Name"))
            .or_else(|| text_of(obj, &format!("{prefix}.Unit")))
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty());
        if is_x {
            d.x_axis_address = addr;
            d.x_axis_correction = Some(factor);
            d.x_axis_offset = off;
            d.x_label = label;
        } else {
            d.y_axis_address = addr;
            d.y_axis_correction = Some(factor);
            d.y_axis_offset = off;
            d.y_label = label;
        }
    }

    Some(d)
}

/// True when the bytes look like a JSON mappack rather than a binary.
pub fn looks_like_json(data: &[u8]) -> bool {
    let head = &data[..data.len().min(512)];
    let text = String::from_utf8_lossy(head);
    let trimmed = text.trim_start_matches(['\u{feff}', ' ', '\t', '\r', '\n']);
    trimmed.starts_with('{') || trimmed.starts_with('[')
}

/// Byte order the definitions describe, for the project as a whole: the one
/// most of its 16/32-bit maps use. Maps that differ keep their own flag.
pub fn dominant_byte_order(maps: &[DetectedMap]) -> Option<&'static str> {
    let mut lohi = 0usize;
    let mut hilo = 0usize;
    for m in maps {
        if matches!(m.data_type, DataType::Int8 | DataType::UInt8) {
            continue;
        }
        if m.is_little_endian == Some(true) {
            lohi += 1;
        } else {
            hilo += 1;
        }
    }
    if lohi == 0 && hilo == 0 {
        return None;
    }
    Some(if lohi >= hilo { "lohi" } else { "hilo" })
}

#[cfg(test)]
mod tests {
    use super::*;

    const PACK: &str = r#"{"maps":[
      {"Name":"Boost target","FolderName":"Turbo boost pressure","Type":"eZweidim",
       "DataOrg":"eHiLo","bSigned":"0","Columns":"16","Rows":"12","Comment":"target",
       "Fieldvalues.Unit":"mbar","Fieldvalues.Factor":"0.100000","Fieldvalues.Offset":"0",
       "Fieldvalues.StartAddr.Cpu":"$1A2B0","AxisX.Name":"RPM","AxisX.Factor":"1.000000",
       "AxisX.Offset":"0","AxisX.DataAddr.Cpu":"$1A000","AxisY.Name":"IQ",
       "AxisY.Factor":"0.010000","AxisY.Offset":"0","AxisY.DataAddr.Cpu":"$1A100"},
      {"Name":"N75 duty","FolderName":"Z-Other","DataOrg":"eByte","bSigned":"1",
       "Columns":"8","Rows":"1","Fieldvalues.Factor":"0.5","Fieldvalues.Offset":"-10",
       "Fieldvalues.StartAddr.Cpu":"$1B000","AxisX.DataAddr.Cpu":"$1B100"},
      {"Name":"Outside the file","DataOrg":"eLoHi","Columns":"16","Rows":"16",
       "Fieldvalues.StartAddr.Cpu":"$FFFF00"},
      {"Name":"","DataOrg":"eLoHi","Columns":"2","Rows":"2","Fieldvalues.StartAddr.Cpu":"$100"}
    ]}"#;

    #[test]
    fn reads_a_two_dimensional_map() {
        let maps = parse_mappack(PACK, 0x100000).unwrap();
        let m = maps.iter().find(|m| m.name.as_deref() == Some("Boost target")).unwrap();
        assert_eq!(m.address, 0x1A2B0);
        assert!(matches!(m.dimensions, MapDimensions::TwoDimensional { rows: 12, cols: 16 }));
        assert_eq!(m.size, 12 * 16 * 2);
        assert!(matches!(m.data_type, DataType::UInt16));
        assert_eq!(m.is_little_endian, None, "eHiLo = gros-boutiste, pas de drapeau");
        assert_eq!(m.category.as_deref(), Some("Turbo boost pressure"));
        assert_eq!(m.unit.as_deref(), Some("mbar"));
        assert!((m.correction_factor.unwrap() - 0.1).abs() < 1e-12);
        assert_eq!(m.x_axis_address, Some(0x1A000));
        assert_eq!(m.y_axis_address, Some(0x1A100));
        assert!((m.y_axis_correction.unwrap() - 0.01).abs() < 1e-12);
        assert_eq!(m.x_label.as_deref(), Some("RPM"));
        assert_eq!(m.external_source.as_deref(), Some("JSON"));
    }

    #[test]
    fn a_single_row_is_read_as_a_curve() {
        let maps = parse_mappack(PACK, 0x100000).unwrap();
        let m = maps.iter().find(|m| m.name.as_deref() == Some("N75 duty")).unwrap();
        assert!(matches!(m.dimensions, MapDimensions::OneDimensional { length: 8 }));
        assert!(matches!(m.data_type, DataType::Int8));
        assert_eq!(m.category.as_deref(), Some("Other"), "le prefixe Z- de l'export tombe");
        assert!((m.offset.unwrap() + 10.0).abs() < 1e-12);
    }

    #[test]
    fn maps_outside_the_binary_or_without_a_name_are_skipped() {
        let maps = parse_mappack(PACK, 0x100000).unwrap();
        assert_eq!(maps.len(), 2);
        assert!(!maps.iter().any(|m| m.name.as_deref() == Some("Outside the file")));
    }

    #[test]
    fn accepts_numbers_a_bare_array_and_nested_objects() {
        let json = r#"[{"name":"Rail pressure","address":4096,"rows":8,"cols":4,
          "DataOrg":"eLoHi","factor":0.25,"offset":0,
          "Fieldvalues":{"Unit":"bar"},"x_axis_address":8192}]"#;
        let maps = parse_mappack(json, 0x10000).unwrap();
        assert_eq!(maps.len(), 1);
        let m = &maps[0];
        assert_eq!(m.address, 4096);
        assert_eq!(m.unit.as_deref(), Some("bar"));
        assert_eq!(m.is_little_endian, Some(true));
        assert_eq!(m.x_axis_address, Some(8192));
        assert!((m.correction_factor.unwrap() - 0.25).abs() < 1e-12);
    }

    #[test]
    fn byte_order_follows_the_majority() {
        let maps = parse_mappack(PACK, 0x100000).unwrap();
        assert_eq!(dominant_byte_order(&maps), Some("hilo"));
        assert_eq!(dominant_byte_order(&[]), None);
    }

    #[test]
    fn a_file_that_is_not_a_mappack_is_refused() {
        assert!(parse_mappack("not json", 0).is_err());
        assert!(parse_mappack(r#"{"hello":1}"#, 0).is_err());
        assert!(looks_like_json(b"  {\"maps\": []}"));
        assert!(!looks_like_json(&[0u8, 1, 2, 3]));
    }
}
