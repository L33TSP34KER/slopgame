use bevy::time::common_conditions::*;

use core::time::Duration;

use bevy::prelude::*;

#[derive(Component)]
struct Speed(f32);
#[derive(Component)]
struct Power(f32);
#[derive(Component, Default)]
struct Velocity(Vec2);

#[derive(Resource, Default)]
struct WaveManager {
    current_wave: u32,
    enemies_to_spawn: u32,
    enemies_alive: u32,
}

#[derive(Component)]
struct WaveText;

#[derive(Component)]
#[require(Speed, Health)]
struct Player;

#[derive(Component)]
#[require(Speed, Health)]
struct Enemy;

#[derive(Component)]
#[require(Velocity, Speed)]
struct Bullet;

impl Default for Speed {
    fn default() -> Self {
        Speed(200.0)
    }
}

#[derive(Component)]
struct Health {
    current: f32,
    max: f32,
}

impl Default for Health {
    fn default() -> Self {
        Health {
            current: 100.0,
            max: 100.0,
        }
    }
}

#[derive(States, Default, Debug, Clone, PartialEq, Eq, Hash)]
enum GameState {
    #[default]
    Playing,
}

fn main() {
    App::new()
        .add_plugins(DefaultPlugins)
        .init_state::<GameState>()
        .add_systems(Startup, setup)
        .add_systems(Update, move_player)
        .add_systems(Update, tick_update.run_if(on_timer(Duration::from_secs(2))))
        .add_systems(
            Update,
            shoot_bullet.run_if(on_timer(Duration::from_secs(1))),
        )
        .add_systems(Update, chase_player.run_if(in_state(GameState::Playing)))
        .insert_resource(Time::<Fixed>::from_hz(20.0)) // 20 ticks/second
        .add_systems(FixedUpdate, game_logic)
        .add_systems(FixedUpdate, move_bullets)
        .add_systems(FixedUpdate, bullet_collision)
        .run();
}

fn shoot_bullet(
    mut commands: Commands,
    time: Res<Time>,
    player: Query<&Transform, With<Player>>,
    mut enemies: Query<(&mut Transform, &Speed), (With<Enemy>, Without<Player>)>,
) {
    let Ok(player_tf) = player.single() else {
        return;
    };

    let closest = enemies
        .iter()
        .map(|(tf, _)| tf.translation.truncate())
        .min_by(|a, b| {
            a.distance_squared(player_tf.translation.truncate())
                .total_cmp(&b.distance_squared(player_tf.translation.truncate()))
        });
    let Some(target) = closest else { return };

    let dir = (target - player_tf.translation.truncate()).normalize_or_zero();

    commands.spawn((
        DespawnOnExit(GameState::Playing),
        Bullet,
        Velocity(dir * 600.0),
        Sprite::from_color(Color::srgb(0.5, 0.0, 0.0), Vec2::splat(5.0)),
        Transform::from_translation(player_tf.translation),
    ));
}

fn game_logic(
    mut commands: Commands,
    time: Res<Time>,
    player: Query<&Transform, With<Player>>,
    mut enemies: Query<(&mut Transform, &Speed), (With<Enemy>, Without<Player>)>,
) {
    let Ok(player_tf) = player.single() else {
        return;
    };

    for (mut enemy_tf, speed) in &mut enemies {
        let to_player = player_tf.translation.truncate() - enemy_tf.translation.truncate();
        let dir = to_player.normalize_or_zero();
        enemy_tf.translation += (dir * speed.0 * time.delta_secs()).extend(0.0);
    }
}

fn move_bullets(time: Res<Time>, mut bullets: Query<(&mut Transform, &Velocity), With<Bullet>>) {
    for (mut tf, vel) in &mut bullets {
        tf.translation += (vel.0 * time.delta_secs()).extend(0.0);
    }
}

fn bullet_collision(
    mut commands: Commands,
    bullets: Query<(Entity, &Transform), With<Bullet>>,
    mut enemies: Query<(Entity, &mut Health, &Transform), With<Enemy>>,
    mut wave_manager: ResMut<WaveManager>,
) {
    for (bullet_entity, bullet_tf) in &bullets {
        for (enemy_entity, mut health, enemy_tf) in &mut enemies {
            let distance = bullet_tf.translation.distance(enemy_tf.translation);
            if distance < 30.0 {
                health.current -= 1.0;
                commands.entity(bullet_entity).despawn();
                if health.current <= 0.0 {
                    commands.entity(enemy_entity).despawn();
                    wave_manager.enemies_alive -= 1;
                }
                break;
            }
        }
    }
}

fn chase_player(
    time: Res<Time>,
    player: Query<&Transform, With<Player>>,
    mut enemies: Query<(&mut Transform, &Speed), (With<Enemy>, Without<Player>)>,
) {
    let Ok(player_tf) = player.single() else {
        return;
    };

    for (mut enemy_tf, speed) in &mut enemies {
        let to_player = player_tf.translation.truncate() - enemy_tf.translation.truncate();
        let dir = to_player.normalize_or_zero();
        enemy_tf.translation += (dir * speed.0 * time.delta_secs()).extend(0.0);
    }
}

fn tick_update(mut commands: Commands) {
    commands.spawn((
        (Enemy, Speed(30.0), Health { current: 1.0, max: 1.0 }),
        Sprite::from_color(Color::srgb(0.5, 0.0, 0.0), Vec2::splat(50.0)),
        Transform::default(),
    ));
}

fn setup(mut commands: Commands) {
    commands.spawn(Camera2d);
    commands.spawn((
        (Player, Speed(300.0)),
        Sprite::from_color(Color::srgb(0.2, 0.7, 1.0), Vec2::splat(50.0)),
        Transform::default(),
    ));
}

fn move_player(
    input: Res<ButtonInput<KeyCode>>,
    time: Res<Time>,
    mut query: Query<(&mut Transform, &mut Speed), With<Player>>,
) {
    let Ok((mut transform, speed)) = query.single_mut() else {
        return;
    };
    let mut dir = Vec2::ZERO;
    if input.pressed(KeyCode::KeyA) {
        dir.x -= 1.0;
    }
    if input.pressed(KeyCode::KeyD) {
        dir.x += 1.0;
    }
    if input.pressed(KeyCode::KeyW) {
        dir.y += 1.0;
    }
    if input.pressed(KeyCode::KeyS) {
        dir.y -= 1.0;
    }
    transform.translation += (dir.normalize_or_zero() * speed.0 * time.delta_secs()).extend(0.0);
}
