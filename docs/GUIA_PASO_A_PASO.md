# Cómo explicar el analizador INA128P

## 1. La idea en una frase

> El programa configura una frecuencia, mide tensión y corriente, calcula la
> impedancia y muestra el resultado. Si hay una calibración válida, primero
> corrige la ganancia y el error de fase.

El barrido repite esta misma medición para varias frecuencias. La calibración
repite las lecturas usando una resistencia de valor conocido.

## 2. Qué mide el circuito

```text
Generador ── A ── Rs ── B (V2) ── Zx ── masa
             │         ├── CH2
             │         └── Vin− del INA128P
             └──────────── Vin+ del INA128P

Salida Vo del INA128P ── CH1
REF del INA128P y masas de las sondas ── masa
```

- **Rs:** resistencia sensora, cuyo valor conoce el programa.
- **Zx:** componente desconocido que queremos medir.
- **Vo / CH1:** salida del INA128P. Representa la caída sobre Rs amplificada.
- **VZ / CH2:** tensión en V2, sobre el componente.
- **RG:** resistencia que fija la ganancia del INA128P.
- **REF:** conectado a masa en esta placa.

La corriente pasa por Rs y por Zx. Con las entradas conectadas como indica el
esquema, el amplificador entrega una salida proporcional a esa corriente:

```text
G = 1 + 50000/RG
Vo = G × I × Rs
I = Vo/(G × Rs)
```

Con RG = 12500 Ω, G = 5. La placa es no inversora: no se resta 180° a la fase.
La fase que se lee es la de CH2 respecto de CH1.

## 3. El orden recomendado para leer el código

| Orden | Archivo | Qué explicar |
|---|---|---|
| 1 | `Codigo/configuracion.py` | Los valores Rs, RG y la ganancia nominal |
| 2 | `Codigo/modelos.py` | Los datos que entran y salen de las funciones |
| 3 | `Codigo/calculos.py` | Las fórmulas de corriente, impedancia, ESR, C y L |
| 4 | `Codigo/operaciones.py` | Cómo se unen las etapas de una medición y un barrido |
| 5 | `Codigo/instrumentos.py` | Cómo se programa el generador y se lee el osciloscopio |
| 6 | `Codigo/calibracion.py` | Cómo se obtiene y se elige la corrección |
| 7 | `Codigo/interfaz/aplicacion.py` | Qué función se ejecuta al pulsar cada botón |

Después se pueden explicar los detalles de `osciloscopios.py`,
`analisis_senoidal.py`, la cancelación y las tareas en segundo plano.

## 4. Desde que se abre el programa hasta que aparece la pantalla

1. `iniciar.sh` ejecuta `Codigo/Interfaz.py` con el Python del proyecto.
2. `Interfaz.py` llama a `main()` de `interfaz/aplicacion.py`.
3. `main()` crea la ventana con `tk.Tk()`.
4. `Aplicacion(root)` crea los paneles y carga la configuración y la calibración
   guardadas. La aplicación de calibración empieza desmarcada.
5. `root.mainloop()` mantiene la ventana esperando acciones del usuario.

**Importante:** abrir la ventana no inicia mediciones ni consultas USB periódicas.

## 5. Qué ocurre al pulsar «Medir»

El recorrido real es:

```text
Aplicacion.medir()
  → operaciones.medir()
    → conectar()
    → medir_una_frecuencia()
      → adquirir()
        → Sesion.preparar()
        → Sesion.leer()
        → procesar_lectura()
          → calibracion.seleccionar()
          → calculos.calcular()
  → PanelMedicion.mostrar()
```

Paso a paso:

1. La interfaz lee Rs, RG, frecuencia, promedio y la casilla de calibración.
2. Revisa que los números sean válidos y bloquea los controles mientras trabaja.
3. `conectar()` abre una sesión VISA y encuentra un osciloscopio y un generador.
4. `Sesion.preparar()` programa la frecuencia, espera 0,5 s, ejecuta Autoset
   y espera otros 3 s para estabilizar la lectura.
5. `Sesion.leer()` devuelve `Lectura(vo, vz, frecuencia, fase)`.
6. `calibracion.seleccionar()` decide si corresponde usar correcciones o valores
   nominales. Devuelve un objeto `Ajuste`.
7. `calculos.calcular()` obtiene los parámetros del componente.
8. Al salir de `with conectar(...)`, se cierran los recursos de comunicación.
9. La interfaz recibe el objeto `Medicion` y muestra sus valores con unidades.

La **frecuencia programada** es la solicitada. La **frecuencia medida** viene
del osciloscopio y es la utilizada para calcular L o C. Si difieren más del 5%,
la captura se considera inválida y se reintenta.

### Por qué `adquirir()` recibe una función `procesar`

Se utiliza el mismo recorrido para medir y calibrar. Lo que cambia es qué se
hace con las cuatro lecturas:

- Al medir, `procesar_lectura()` calcula una impedancia.
- Al calibrar, `procesar_referencia()` calcula ganancia y error de fase.
- En abierto, `procesar_abierto()` reúne tres capturas y comprueba su estabilidad.

`adquirir()` llama a la función correspondiente después de leer. Así, si una
lectura **o su cálculo** falla, se repite la adquisición completa. Hay un intento
inicial y hasta tres reintentos. Una cancelación se propaga sin reintentarse.

## 6. Las cuentas de `calculos.py`, en orden

### Caso habitual: sin residual de circuito abierto

1. Elegir **G**: nominal o medida durante la calibración.
2. Calcular `I = Vo/(G × Rs)`.
3. Calcular `|Z| = VZ/I`.
4. Corregir la fase: `fase_corregida = fase_medida − correccion_de_calibracion`.
5. Separar las componentes: `ESR = |Z| × cos(fase)` y `Xs = |Z| × sin(fase)`.
6. Comprobar que la impedancia sea finita y que ESR no sea negativa.
7. Clasificar el componente por el signo de Xs.

Los ángulos se convierten a radianes para `sin()` y `cos()`.

| Condición | Tipo | Valor | Factor |
|---|---|---|---|
| Xs = 0 | Resistencia | R = ESR | No corresponde |
| Xs > 0 | Inductor | L = Xs/(2πf) | Q = Xs/ESR |
| Xs < 0 | Capacitor | C = 1/(2πf·\|Xs\|) | D = ESR/\|Xs\| |

Para un inductor con ESR = 0, Q es infinito y se muestra así, sin dividir por cero.
No hay una banda de ±2° para considerar una resistencia: la clasificación sigue
el signo de la reactancia calculada.

En Python, `complex(ESR, Xs)` guarda ambas partes en `z`: `z.real` es ESR,
`z.imag` es Xs y `abs(z)` es el módulo. Esto permite conservarlas juntas.
`normalizar_fase()` solo lleva el ángulo al intervalo −180° a 180°;
**no añade una inversión física al INA128P**.

### Ejemplo numérico sencillo

```text
Rs = 10 Ω; RG = 12500 Ω → G = 5
Vo = 0,050 V RMS; VZ = 0,100 V RMS; fase = 0°
I = 0,050/(5 × 10) = 0,001 A = 1 mA
|Z| = 0,100/0,001 = 100 Ω
ESR = 100 × cos(0°) = 100 Ω
Xs = 100 × sin(0°) = 0 Ω
Resultado: resistencia de 100 Ω
```

Podés ejecutar **el cálculo real del programa** con esos datos simulados:

```bash
.venv/bin/python ejemplos/medicion_paso_a_paso.py
```

Ese ejemplo no abre la interfaz, no usa USB y no modifica la calibración.

## 7. Cómo se obtiene la calibración

Se coloca una resistencia conocida `Rref` en lugar de Zx. Para cada frecuencia:

1. Se miden Vo, VZ y fase.
2. Como Rref es conocida, se calcula `Iref = VZ/Rref`.
3. La caída sobre la sensora es `Vrs = Iref × Rs`.
4. La ganancia medida es `G_medida = Vo/Vrs`.
5. La resistencia de referencia tiene fase ideal cero: el desfase leído es
   el error que hay que restar en las mediciones posteriores.
6. Se guarda ese punto con frecuencia, ganancia y corrección de fase.

`operaciones.calibrar()` repite estos pasos. Solo si termina todo el barrido,
la interfaz guarda el perfil en `datos/calibracion-ina128p.json` y lo activa.
Si falla o se cancela, conserva el archivo anterior.

### Cómo decide si puede aplicarla

`calibracion.seleccionar()` comprueba la casilla del usuario, la existencia del
perfil, Rs, RG, el equipo, el método y la frecuencia.

- Si corresponde, aplica el perfil.
- Entre dos puntos calibrados, interpola sus correcciones.
- Fuera del rango o con una configuración no cubierta, usa G nominal,
  corrección de fase 0° y residual 0. La pantalla indica el motivo.
- Se admite una pequeña diferencia de reloj en la frecuencia medida de los
  extremos, siempre que la frecuencia solicitada esté dentro del rango.

Por ejemplo, entre 1000 Hz y 2000 Hz, 1500 Hz tiene peso 0,5:

```text
peso = (1500 − 1000)/(2000 − 1000) = 0,5
G = G_inicial + peso × (G_final − G_inicial)
Si G_inicial = 4,8 y G_final = 4,6, G = 4,7.
```

La fase se interpola teniendo en cuenta que los ángulos son circulares.

### Apartado adicional: circuito abierto

Este paso es opcional. Se usa si existe una señal residual medible aun sin Zx.
Se comprueba que sea estable entre tres capturas y se obtiene `h`.
Con la resistencia conocida se calcula `A = Rref × (m_ref − h)`.
En la medición se aplica `Z = A/(m − h)`, donde `m` es Vo/VZ incluyendo su fase.

En ese caso la corriente se obtiene de `I = VZ/|Z|` después de compensar el
residual. No alcanza con dividir directamente Vo por G·Rs, porque Vo incluye
la señal residual. Este cálculo queda separado dentro de `calcular()`.

## 8. Cómo se hace el barrido y cómo se cancela

`operaciones.barrer()`:

1. Construye la lista de frecuencias con inicio, final y cantidad de puntos.
2. Abre una sesión de comunicación para el barrido.
3. Recorre la lista con un `for`.
4. Para cada frecuencia llama a `medir_una_frecuencia()`, igual que la medición simple.
5. Guarda una `Fila` con el resultado o el error y actualiza la tabla.
6. Al finalizar, libera los equipos y conserva las filas.

El botón Cancelar activa una señal de parada. `control.comprobar()` consulta
esa señal entre etapas. `control.esperar()` permite interrumpir las pausas.
La excepción `Cancelado` sale del recorrido sin iniciar nuevas frecuencias.
Si un comando USB está en curso, se espera su finalización o timeout para poder
liberar los recursos. Los resultados ya obtenidos permanecen en la tabla.
Cancelar conserva la última frecuencia programada en el generador.

## 9. Comunicación, captura y promedio

`instrumentos_usb.py` detecta los dispositivos y consulta su identificación
cuando el usuario pulsa Actualizar equipos. El botón Habilitar acceso USB
solicita la autorización de Linux mediante `linux/configurar_usb.py` si faltan
permisos. Estas funciones no miden impedancias.

`instrumentos.py` abre y cierra VISA; `osciloscopios.py` reúne los comandos propios
de cada familia de osciloscopios. Algunos comandos utilizados son:

| Comando | Para qué se usa |
|---|---|
| `*IDN?` | Pedir fabricante, modelo y serie |
| `:CHANnel1:BASE:FREQuency ...` | Programar el generador |
| `AUTOSet EXECute` | Ajustar el Tektronix automáticamente |
| `CURVe?` | Descargar muestras del canal seleccionado |

En Tektronix se congelan ambos canales de una misma captura. Se descargan las
muestras y se convierten los códigos del ADC a voltios usando los parámetros
del osciloscopio. `analisis_senoidal.py` ajusta una senoide más una continua:

```text
señal(t) = A × sin(2πft) + B × cos(2πft) + continua
RMS de la fundamental = sqrt(A² + B²)/sqrt(2)
```

El código busca la frecuencia que mejor ajusta CH2, luego obtiene amplitud y
fase de los dos canales usando ese mismo tiempo y esa misma frecuencia.
Comprueba también si hay demasiado ruido o distorsión.

El promedio combina formas de onda sincronizadas a la misma frecuencia antes
de calcular la impedancia. Con tiempo ajustable, el Tektronix usa hasta 512
adquisiciones y después promedio exponencial; el programa comprueba que haya
adquisiciones nuevas. UNI-T utiliza sus consultas automáticas de RMS y fase.

## 10. Por qué la ventana puede responder mientras se mide

`interfaz/tareas.py` ejecuta las operaciones en un hilo de trabajo. El hilo envía
progreso y resultados a una cola. La ventana consulta esa cola con `after()` y
actualiza sus controles desde el hilo principal de Tk.

Esto permite cancelar sin congelar la interfaz. Las comunicaciones físicas son
las mismas; lo que cambia es dónde se ejecutan mientras la pantalla responde.

## 11. Sintaxis de Python que conviene explicar

| Expresión | Explicación breve |
|---|---|
| `def` | Define una función |
| `class` | Agrupa datos y acciones de un mismo objeto |
| `self` | El objeto al que pertenece ese método |
| `@dataclass` | Crea una clase para guardar campos de datos |
| `frozen=True` | Impide reasignar sus campos después de crear el objeto |
| `@property` | Permite leer un cálculo como `configuracion.ganancia` |
| `None` | No hay un valor; por ejemplo, no hay perfil de calibración |
| `with conectar(...)` | Usa la sesión y garantiza ejecutar su cierre al salir |
| `try` / `except` | Ejecuta pasos y maneja sus errores |
| `return` | Devuelve un resultado al código que llamó la función |
| `progreso` | Función que informa a la pantalla cómo avanza el trabajo |

Una `Lectura` contiene lo que llegó del equipo. Un `Ajuste` contiene la corrección
elegida. Una `Medicion` contiene lo calculado. Una `Fila` contiene lo que se muestra
en una frecuencia del barrido. Mantener esos nombres ayuda a seguir el recorrido.

## 12. Guion corto para presentar

> Primero ingreso Rs, RG y la frecuencia. El programa obtiene la ganancia nominal
> del INA128P y se comunica con el generador y el osciloscopio por USB. Programa
> la frecuencia, adquiere las señales de corriente y tensión, y decide si puede
> aplicar la calibración. Calcula corriente, módulo de impedancia, ESR y
> reactancia; con el signo de la reactancia identifica R, L o C. Un barrido repite
> el mismo procedimiento y guarda cada frecuencia en una tabla. Si cancelo,
> conserva los resultados obtenidos y libera los equipos.
