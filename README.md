# Analizador de impedancias — MEII

## Seleccionar «Actual» u «Original»

El selector **Modo de medición**, en Configuración de Hardware, se aplica
tanto a Medición Simple como al Barrido. Al iniciar se mantiene **Actual**.

- **Actual:** conserva la captura senoidal Tektronix y la calibración existentes.
- **Original:** reproduce adquisición y cálculos del backend del commit
  `03d21e8`, con las consultas automáticas RMS, frecuencia y fase adaptadas
  al Tektronix TBS2000B. No descarga muestras ni aplica ajuste senoidal.
  Mantiene ganancia 5, resta de 180°, clasificación resistiva entre −2° y +2°,
  ESR negativa convertida en cero y factores D/Q originales.
  La medición simple lee la frecuencia y no hace Autoset. El barrido usa la
  frecuencia programada, hace Autoset en cada punto y omite un punto fallido
  sin repetir toda la adquisición; conserva los reintentos de lecturas textuales.
  Los gráficos conservan las series y el tipo final del barrido original.

En Original no se aplica ningún perfil de calibración, aunque esté guardado.
Sus controles de adquisición de calibración quedan deshabilitados; al regresar
a Actual se conserva la selección anterior y el perfil. El modo no puede
cambiarse durante una medición. CH1 debe estar en I_OUT y CH2 en V_OUT.
El Tektronix debe estar adquiriendo y tener ambos canales visibles para la
medición simple. Las consultas de medida inmediata esperan su actualización
y restauran tipo, fuentes y gating al terminar.

En Tektronix se configura `MEASUrement:IMMed:SOUrce1 CH2` (target) y
`SOUrce2 CH1` (reference). La fase es positiva si CH2 adelanta a CH1;
se conserva su signo antes de aplicar la corrección original de inversión.
Se usa `RMS` sobre el registro completo, no `CRMs` ni la fundamental.
El barrido conserva las pausas originales de 0,5 s después de programar el
generador y 3 s después de Autoset; cada cambio de medida inmediata Tektronix
añade 0,3 s para permitir su actualización. Las respuestas textuales inválidas
se consultan hasta cinco veces con pausas de 1 s, como en `03d21e8`.
La convención y los comandos se consultaron en el
[manual de programación TBS2000B, pp. 131–134](https://download.tek.com/manual/TBS2000B-Programmer-Manual-EN-US-077114904.pdf)
y el [algoritmo de fase publicado por Tektronix](https://download.tek.com/manual/070921900.pdf).

Se comprobó `main` de GitHub el 13/10/2026 mediante `git ls-remote`:
apunta a `03d21e88dad6539eeab2453c20b19680413ed4e5`, sin cambios posteriores.

La equivalencia corresponde al algoritmo original; las mediciones internas
de dos marcas de osciloscopios pueden tener diferencias. Este modo no fuerza
igualdad de resultados entre instrumentos.

## Abrir en esta PC

Buscá **ME2 - Analizador de impedancias** en el menú de aplicaciones.
También podés ejecutar desde la carpeta del proyecto:

```bash
./iniciar.sh
```

Conectá por USB y encendé el osciloscopio UNI-T o Tektronix TBS2102B y el generador UTG1042X.
La medición simple requiere el osciloscopio; el barrido requiere ambos equipos.
Seleccioná la resistencia sensora real del circuito antes de medir.

El programa toma la señal de corriente de CH1 y la tensión de CH2.
Sin calibración usa ganancia nominal 5 y corrección de inversión de 180°.
Con calibración compensa la transferencia y la señal residual medidas para cada frecuencia.

## Osciloscopios UNI-T y Tektronix

El programa consulta `*IDN?` al iniciar una operación y elige automáticamente
los comandos correspondientes. Ambos usan VISA sobre USBTMC; no usan un puerto
serie ni requieren configurar baudios. La etiqueta de equipos se actualiza
únicamente al pulsar **Actualizar equipos**.

- **UNI-T DSO/UTD:** conserva las consultas directas de RMS, frecuencia y fase
  que utilizaba el proyecto.
- **Tektronix TBS2000B:** obtiene una estimación de frecuencia de CH2 con
  `MEASUrement:IMMed:VALue?`, configura una ventana de cinco ciclos y adquiere
  un registro de 20 000 muestras. Espera el fin de adquisición con `*OPC?` y
  descarga ambos canales de esa misma captura con `CURVe?`. Calcula la
  frecuencia, las tensiones RMS de la fundamental y la fase CH2−CH1 por ajuste
  senoidal, incluyendo un término de continua. Así evita depender de los
  cruces de nivel o del número de ciclos completos de la ventana.
  El ajuste automático usa `AUTOSet EXECute`, habilita CH1/CH2 y acoplamiento
  DC. Luego centra ambos canales, ajusta sus escalas a unas seis divisiones
  pico a pico y obtiene el promedio de 16 adquisiciones sincronizadas.
  Se ejecuta también en la medición simple al cambiar Zx. La adquisición
  y los parámetros de transferencia se restauran al terminar, incluso si
  falla la lectura; las nuevas escalas quedan visibles en el osciloscopio.

El método de captura rechaza transferencias incompletas, canales sin un eje
de tiempo común, recorte del ADC y señales con más de 5% de residuo respecto
de la fundamental (ruido/distorsión). Requiere al menos 2,5 ciclos y 20 muestras
por ciclo. No modifica la frecuencia ni la amplitud del generador en una
medición simple. UNI-T conserva su método de consultas SCPI directas.

El soporte Tektronix corresponde a TBS2072B, TBS2074B, **TBS2102B**, TBS2104B,
TBS2202B y TBS2204B, incluidos en el
[manual oficial 077114904](https://www.tek.com/en/manual/oscilloscope/tbs2000b-series-programmer-manual-tbs2000).
Se verificaron la comunicación, ambas lecturas RMS, frecuencia, fase y Autoset
con el TBS2102B conectado, serie C022681. Otros modelos Tektronix requieren
verificar su manual y muestran un error explícito; no se les envían comandos
UNI-T. Para medir, mantené CH1 en I_OUT y CH2 en V_OUT, con los dos canales
visibles y el osciloscopio adquiriendo señales.

Conectá un solo osciloscopio compatible a la vez. Si hay dos, el programa pide
dejar conectado el que se quiere usar, para evitar medir con el equipo equivocado.

## Calibración de fase y ganancia

1. Seleccioná R1 real y elegí el rango de frecuencia y la cantidad de puntos.
2. Retirá Zx sin mover las sondas ni R1. Pulsá **1. Medir circuito abierto**.
   Este paso registra la señal residual de la cadena sin corriente en Zx.
3. Colocá una resistencia conocida que se comporte como resistencia en todo
   el rango. Ingresá su valor en Ω (por ejemplo `1800` para 1,8 kΩ).
4. Pulsá **2. Medir resistencia y guardar**. El campo de resistencia es editable
   en cada ensayo. Si cambiás R1, el rango o la cantidad de puntos, repetí el
   circuito abierto. Ambos pasos requieren el osciloscopio y el generador.
5. La tabla y **Ver curvas** muestran ganancia y fase del amplificador después
   de separar el residual. Una calibración completa se guarda y activa.
6. Volvé a colocar Zx para medir, manteniendo R1, sondas y conexiones.

Se utiliza un modelo complejo de la fundamental:

```text
m = (I_OUT_RMS / V_OUT_RMS) · exp(-j · fase_medida)
h(f) = m_circuito_abierto
A(f) = R_conocida · (m_referencia - h)
G(f) = |A(f)| / R1
corrección_fase = normalizar(-arg(A) - 180°)
Zx(f) = A(f) / (m_medida - h(f))
```

La calibración anterior, con una sola resistencia, suponía que todo el error
era multiplicativo. Una señal residual puede sesgar esa ganancia y fase al
cambiar de una resistencia grande a un inductor de impedancia menor. El paso
abierto permite estimar por separado ese término aditivo. Este modelo supone
que la cadena es lineal y que el residual se conserva al cambiar Zx.

Los coeficientes complejos A y h se interpolan linealmente entre frecuencias
calibradas. No se extrapola fuera del rango ni se aplica el perfil a otra R1.
Se tolera un desvío de reloj de hasta 0,1% en los extremos usando su coeficiente.
**Aplicar calibración** permite volver al modelo nominal.

En abierto, el Tektronix promedia 128 adquisiciones y captura unos 20 ciclos.
La señal de CH1 puede ser demasiado pequeña para exigir un residuo del 5%
respecto de su propia fundamental: en este paso se exige ruido residual menor
al 0,1% de V_OUT y tres capturas cuyo fasor difiera menos del 1% de su promedio.
CH2 conserva el límite del 5%. Las mediciones normales mantienen ambos límites
del 5%. Si no se puede medir un residual estable, no se guarda una calibración.
Una corriente que no se distingue del residual produce un error de lectura.

El perfil se guarda en `datos/calibracion.json` y se carga al volver a abrir.
Si falla un punto, el perfil nuevo no se aplica ni reemplaza el anterior. Los perfiles
antiguos sin circuito abierto se cargan desactivados y pueden consultarse.
El perfil representa la respuesta conjunta de la cadena de medición; si cambiás
el osciloscopio, el amplificador, las sondas o conexiones, realizá una nueva calibración.
Los perfiles nuevos guardan el modelo y número de serie del osciloscopio y no
se aplican a otro equipo. Los perfiles anteriores sin identificación siguen
siendo utilizables con UNI-T; con Tektronix se requiere una nueva calibración
o desactivar **Aplicar calibración**.

Las calibraciones Tektronix realizadas antes del método de captura senoidal
se conservan en disco pero se desactivan al abrir el programa. Es necesario
repetirlas con circuito abierto y resistencia conocida; el archivo nuevo registra
`metodo_medicion: senoidal_v1`. El inductor no sustituye esa resistencia durante
la calibración.

Cada punto de referencia debe ser coherente con el amplificador inversor:
la corrección respecto de 180° debe ser menor que 90° en valor absoluto, y
la variación circular entre puntos vecinos no debe superar 45°. Un punto
incoherente activa los tres reintentos; si persiste, el perfil nuevo no se
aplica. Si la respuesta cambia demasiado entre puntos, usá más puntos o
limitá el rango. Se comprueban estas condiciones también al cargar un perfil.

## Validación de mediciones

Las lecturas cero o negativas de RMS/frecuencia, valores no finitos y códigos
numéricos de error se rechazan. Una ESR negativa produce un error en lugar de
convertirse en cero. La identificación usa el signo de la fase corregida:
negativa para capacitor, positiva para inductor y cero para resistencia.
En barridos se comprueba además que la frecuencia medida esté dentro del
5% de la programada, para rechazar capturas de una frecuencia anterior.

El barrido conserva el tipo de cada punto. Las curvas de capacitancia (F),
inductancia (H), D y Q se presentan por separado, sin mezclar magnitudes ni
unidades cuando cambia la clasificación.

Si falla una medición simple o un punto del barrido o de la calibración, se repite la adquisición
completa en la misma frecuencia hasta tres veces adicionales (cuatro intentos
en total). La ventana indica el reintento en curso. Solo se registra un punto
cuando su lectura y sus cálculos son válidos. Si se agotan los intentos, el
barrido omite ese punto; la calibración queda incompleta y conserva el perfil
anterior. El archivo de calibración registra cuántos intentos necesitó cada punto.

## Acceso USB en Linux

Pulsá **Actualizar equipos** para detectar los instrumentos USBTMC conectados.
La etiqueta **Equipos conectados** muestra el nombre, número de serie y estado
de cada instrumento según esa última consulta. La actualización es exclusivamente
manual: no se consulta al abrir, periódicamente ni al conectar o desconectar
equipos. El botón queda deshabilitado durante mediciones o barridos.

Si un instrumento nuevo no tiene acceso, aparece **requiere permiso USB** y se
habilita el botón **Habilitar acceso USB**. Pulsalo y autorizá el cambio en la
ventana de Linux. Al terminar, pulsá **Actualizar equipos** para comprobar el
acceso; si cancelás, podés intentarlo nuevamente. La configuración persiste al
reiniciar.

También podés configurar los dos equipos originales desde una terminal:

```bash
./linux/configurar-usb.sh
```

Linux solicita la contraseña de administrador en su ventana de autorización.
El botón instala reglas únicamente para los identificadores de los instrumentos
USBTMC conectados que necesitan permiso. La detección y autorización aceptan
otros instrumentos USBTMC; las mediciones utilizan los osciloscopios
UNI-T DSO/UTD o Tektronix TBS2000B y generadores UTG compatibles con los comandos del proyecto.
La configuración de terminal sin argumentos usa `5656:0832` y `6656:0834`.
La aplicación se ejecuta con el usuario habitual.

## Reinstalar las dependencias

Se requiere Python 3.12 con Tkinter y libusb. En Ubuntu/Linux Mint, los paquetes
del sistema son `python3-venv`, `python3-tk` y `libusb-1.0-0`.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./iniciar.sh
```

Las lecturas USB se ejecutan en segundo plano para que la ventana siga
respondiendo. Durante una operación, los botones de adquisición y calibración quedan
deshabilitados para evitar conexiones simultáneas a los instrumentos.
