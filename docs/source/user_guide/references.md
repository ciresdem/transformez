# 🗺️ Vertical References

A reference describes the vertical coordinate system or surface that elevations are expressed relative to. Transformez accepts both authority-defined coordinate reference systems, such as `EPSG:5703`, and model-defined surfaces, such as `vdatum:mllw` and `global:lat`.

| Form                  | Example          | Meaning                            |
| --------------------- | ---------------- | ---------------------------------- |
| Authority CRS         | `EPSG:5703`      | Standard CRS resolved through PROJ |
| Transformez reference | `vdatum:mllw`    | Named physical/model surface       |
| Compound CRS          | `EPSG:4326+5703` | Horizontal + vertical CRS          |

Transformez provides custom namespaced vertical references. This is to distinguish common vertical datum types, especially tidal datums, by their provider and provenance. Examples of namespaced custom references include:

```
vdatum:mllw
vdatum:mhw
vdatum:msl

global:lat
global:hat
global:mss
```

This helps differentiate VDatum's realization of MLLW from a global model such as LAT.

Transformez also conceptually seperates vertical references from vertical bindings, where a vertical reference describes what the surface is and the vertical bindings describe how Transformez realizes and operates on that surface. Not all vertical references have a supported vertical binding. Bindings encode things such as `provider`, `engine`, `provider-specific datum`, `native frame`, and `default model` independently of the vertical reference metadata.
