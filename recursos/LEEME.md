# Ícono UTN

- `utn-original.png`: imagen proporcionada por el usuario, conservada sin cambios.
- `utn.png`: símbolo con fondo transparente, conservado como recurso de origen.
- `utn-fondo-blanco.png`: ícono de la ventana y de los accesos de la versión final.
- `circuito-lc.png`: esquema proporcionado para identificar Rs, RG, Zx y los canales.

La ventana utiliza Pillow para ajustar la imagen del circuito a la altura del
panel, conservando sus proporciones. Al tocar el esquema se abre la vista ampliada.
El registro de edición del ícono blanco está en `ICONO_FONDO_BLANCO.txt`.

La preparación utilizó la herramienta integrada de imágenes (image_gen), sin
cambiar los cálculos ni la calibración del analizador.

Prompt utilizado:

> Use case: background-extraction. Asset type: desktop application icon. Edit target: the supplied black UTN symbol. Remove ONLY the baked-in gray/white checkerboard background and replace it with actual fully transparent alpha. Preserve the exact black symbol silhouette, all proportions, thickness, symmetry, and original orientation. Do not redesign or add text, shadows, extra shapes, color, or a badge. Place the full unchanged symbol centered with a small transparent margin so it is not cropped, in a square PNG icon. Background must be genuinely transparent, not a drawn checkerboard.
